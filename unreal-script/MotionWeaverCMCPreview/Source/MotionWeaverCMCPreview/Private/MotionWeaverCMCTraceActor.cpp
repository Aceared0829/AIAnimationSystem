// Copyright ZhaoZining. All Rights Reserved.

/**
 * @file MotionWeaverCMCTraceActor.cpp
 * @brief 在 CMC 移动完成后观测胶囊体 Root，并绘制仅用于诊断的在线速度外推。
 */

#include "MotionWeaverCMCTraceActor.h"
#include "MotionWeaverStancePreviewActor.h"

#include "Camera/CameraActor.h"
#include "DrawDebugHelpers.h"
#include "Engine/Engine.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/CommandLine.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "UnrealClient.h"

DEFINE_LOG_CATEGORY_STATIC(LogMotionWeaverCMCPreview, Log, All);

namespace
{
	constexpr float SampleIntervalSeconds = 1.0f / 30.0f;
	constexpr float PlanHorizonSeconds = 0.75f;
	constexpr int32 MaxSamples = 30 * 60 * 10;
	constexpr int32 MaxTracePoints = 90;
}

AMotionWeaverCMCTraceActor::AMotionWeaverCMCTraceActor()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;
}

void AMotionWeaverCMCTraceActor::BeginPlay()
{
	Super::BeginPlay();
	SampleRows.Reserve(MaxSamples + 1);
	SampleRows.Add(TEXT("time_seconds,cmc_wants_crouch,accepted_crouch,root_x_cm,root_y_cm,root_z_cm,yaw_deg,velocity_x_cm_s,velocity_y_cm_s,velocity_z_cm_s,estimated_x_cm,estimated_y_cm,estimated_z_cm"));
	bAutoTest = FParse::Param(FCommandLine::Get(), TEXT("MotionWeaverAutoTest"));
}

void AMotionWeaverCMCTraceActor::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	ElapsedSeconds += DeltaSeconds;
	SecondsSinceSample += DeltaSeconds;

	if (!TrackedCharacter.IsValid())
	{
		TrackedCharacter = UGameplayStatics::GetPlayerCharacter(this, 0);
	}
	const ACharacter* Character = TrackedCharacter.Get();
	const UCharacterMovementComponent* Movement = Character ? Character->GetCharacterMovement() : nullptr;
	if (!Movement)
	{
		return;
	}
	if (bAutoTest)
	{
		RunAutoTest(*TrackedCharacter.Get());
	}

	const bool bRequestedCrouch = Movement->bWantsToCrouch;
	const bool bAcceptedCrouch = Character->IsCrouched();
	UncrouchPendingSeconds = !bRequestedCrouch && bAcceptedCrouch ? UncrouchPendingSeconds + DeltaSeconds : 0.0f;
	if (bRequestedCrouch != bLastRequestedCrouch || bAcceptedCrouch != bLastAcceptedCrouch)
	{
		UE_LOG(LogMotionWeaverCMCPreview, Display, TEXT("CMC stance request=%d accepted=%d root=%s"), bRequestedCrouch, bAcceptedCrouch, *Character->GetActorLocation().ToCompactString());
		bLastRequestedCrouch = bRequestedCrouch;
		bLastAcceptedCrouch = bAcceptedCrouch;
	}

	if (SecondsSinceSample >= SampleIntervalSeconds)
	{
		RecordSample(*Character);
		SecondsSinceSample = 0.0f;
	}
	DrawTrace(*Character);

	if (GEngine)
	{
		const FString Pending = UncrouchPendingSeconds >= 0.3f ? TEXT(" | UN-CROUCH NOT ACCEPTED") : TEXT("");
		const FString Status = FString::Printf(TEXT("MotionWeaver CMC preview | CMC wants: %s | Actual: %s | Speed: %.0f cm/s%s\nCyan = executed Root, Magenta = velocity-only estimate. Model status appears separately when enabled."),
			bRequestedCrouch ? TEXT("CROUCH") : TEXT("STAND"), bAcceptedCrouch ? TEXT("CROUCH") : TEXT("STAND"), Movement->Velocity.Size2D(), *Pending);
		GEngine->AddOnScreenDebugMessage(270928, 0.25f, FColor::White, Status);
	}
}

void AMotionWeaverCMCTraceActor::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	SaveSamples();
	Super::EndPlay(EndPlayReason);
}

void AMotionWeaverCMCTraceActor::RecordSample(const ACharacter& Character)
{
	if (SampleRows.Num() > MaxSamples)
	{
		return;
	}
	const UCharacterMovementComponent* Movement = Character.GetCharacterMovement();
	const FVector Root = Character.GetActorLocation();
	const FVector Velocity = Movement->Velocity;
	const FVector Estimate = Root + Velocity * PlanHorizonSeconds;
	SampleRows.Add(FString::Printf(TEXT("%.4f,%d,%d,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f"),
		ElapsedSeconds, Movement->bWantsToCrouch, Character.IsCrouched(), Root.X, Root.Y, Root.Z, Character.GetActorRotation().Yaw,
		Velocity.X, Velocity.Y, Velocity.Z, Estimate.X, Estimate.Y, Estimate.Z));
	RecentRootLocations.Add(Root);
	if (RecentRootLocations.Num() > MaxTracePoints)
	{
		RecentRootLocations.RemoveAt(0);
	}
}

void AMotionWeaverCMCTraceActor::DrawTrace(const ACharacter& Character) const
{
#if ENABLE_DRAW_DEBUG
	UWorld* World = GetWorld();
	for (int32 Index = 1; Index < RecentRootLocations.Num(); ++Index)
	{
		DrawDebugLine(World, RecentRootLocations[Index - 1], RecentRootLocations[Index], FColor::Cyan, false, 0.0f, 0, 5.0f);
	}
	const FVector Root = Character.GetActorLocation();
	const FVector Estimate = Root + Character.GetCharacterMovement()->Velocity * PlanHorizonSeconds;
	DrawDebugDirectionalArrow(World, Root, Estimate, 18.0f, FColor::Magenta, false, 0.0f, 0, 5.0f);
#endif
}

void AMotionWeaverCMCTraceActor::RunAutoTest(ACharacter& Character)
{
	if (ElapsedSeconds > 15.0f)
	{
		FinishAutoTest(false, TEXT("timeout"));
		return;
	}
	if (AutoTestPhase == 0 && ElapsedSeconds >= 0.5f)
	{
		AutoTestInitialX = Character.GetActorLocation().X;
		if (APlayerController* Controller = Cast<APlayerController>(Character.GetController()))
		{
			const FVector CameraLocation(AutoTestInitialX + 220.0f, -550.0f, 110.0f);
			const FVector FocusLocation(AutoTestInitialX + 300.0f, 0.0f, 65.0f);
			ACameraActor* Camera = GetWorld()->SpawnActor<ACameraActor>(CameraLocation, (FocusLocation - CameraLocation).Rotation());
			if (Camera)
			{
				Controller->SetViewTarget(Camera);
			}
		}
		Character.Crouch();
		AutoTestPhase = 1;
		AutoTestPhaseStartedSeconds = ElapsedSeconds;
	}
	else if (AutoTestPhase == 1)
	{
		if (Character.IsCrouched())
		{
			AutoTestPhase = 2;
			AutoTestPhaseStartedSeconds = ElapsedSeconds;
		}
		else if (ElapsedSeconds - AutoTestPhaseStartedSeconds > 2.0f)
		{
			FinishAutoTest(false, TEXT("crouch request was not accepted"));
		}
	}
	else if (AutoTestPhase == 2)
	{
		if (Character.GetActorLocation().X < AutoTestInitialX + 300.0f)
		{
			Character.AddMovementInput(FVector::ForwardVector);
		}
		else
		{
			Character.UnCrouch();
			AutoTestPhase = 3;
			AutoTestPhaseStartedSeconds = ElapsedSeconds;
		}
	}
	else if (AutoTestPhase == 3 && ElapsedSeconds - AutoTestPhaseStartedSeconds >= 0.5f)
	{
		if (!Character.IsCrouched())
		{
			FinishAutoTest(false, TEXT("uncrouch was accepted under the low ceiling"));
			return;
		}
		RequestTestScreenshot(TEXT("blocked"));
		AutoTestPhase = 4;
		AutoTestPhaseStartedSeconds = ElapsedSeconds;
	}
	else if (AutoTestPhase == 4)
	{
		if (Character.GetActorLocation().X < AutoTestInitialX + 650.0f)
		{
			Character.AddMovementInput(FVector::ForwardVector);
		}
		else
		{
			Character.UnCrouch();
			AutoTestPhase = 5;
			AutoTestPhaseStartedSeconds = ElapsedSeconds;
		}
	}
	else if (AutoTestPhase == 5 && ElapsedSeconds - AutoTestPhaseStartedSeconds >= 0.5f)
	{
		if (Character.IsCrouched())
		{
			FinishAutoTest(false, TEXT("uncrouch was not accepted after leaving the low ceiling"));
			return;
		}
		RequestTestScreenshot(TEXT("standing"));
		AutoTestPhase = 6;
		AutoTestPhaseStartedSeconds = ElapsedSeconds;
	}
	else if (AutoTestPhase == 6 && ElapsedSeconds - AutoTestPhaseStartedSeconds >= 0.5f)
	{
		FinishAutoTest(true, TEXT("crouch, blocked uncrouch, and later stand observed"));
	}
}

void AMotionWeaverCMCTraceActor::FinishAutoTest(bool bPassed, const TCHAR* Reason)
{
	bAutoTest = false;
	FString ModelFolder;
	if (bPassed && FParse::Value(FCommandLine::Get(), TEXT("MotionWeaverModelFolder="), ModelFolder))
	{
		bool bModelProducedPose = false;
		for (TActorIterator<AMotionWeaverStancePreviewActor> It(GetWorld()); It; ++It)
		{
			bModelProducedPose |= It->HasProducedPose() && It->GetNumInferenceFailures() == 0;
		}
		if (!bModelProducedPose)
		{
			bPassed = false;
			Reason = TEXT("B1 model did not produce a visible pose");
		}
	}
	SaveSamples();
	UE_LOG(LogMotionWeaverCMCPreview, Display, TEXT("MW_CMC_AUTO_TEST_%s: %s"), bPassed ? TEXT("PASS") : TEXT("FAIL"), Reason);
	FPlatformMisc::RequestExitWithStatus(false, bPassed ? 0 : 1);
}

void AMotionWeaverCMCTraceActor::RequestTestScreenshot(const TCHAR* Name) const
{
	const FString Folder = FPaths::ProjectSavedDir() / TEXT("MotionWeaver");
	IFileManager::Get().MakeDirectory(*Folder, true);
	const FString Path = Folder / FString::Printf(TEXT("cmc_%s_%s.png"), Name, *FDateTime::UtcNow().ToString(TEXT("%Y%m%dT%H%M%SZ")));
	FScreenshotRequest::RequestScreenshot(Path, true, false);
}

void AMotionWeaverCMCTraceActor::SaveSamples()
{
	if (bSamplesSaved || SampleRows.Num() <= 1)
	{
		return;
	}
	bSamplesSaved = true;
	const FString Folder = FPaths::ProjectSavedDir() / TEXT("MotionWeaver");
	IFileManager::Get().MakeDirectory(*Folder, true);
	const FString Path = Folder / FString::Printf(TEXT("cmc_preview_%s.csv"), *FDateTime::UtcNow().ToString(TEXT("%Y%m%dT%H%M%SZ")));
	if (FFileHelper::SaveStringArrayToFile(SampleRows, *Path, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM))
	{
		UE_LOG(LogMotionWeaverCMCPreview, Display, TEXT("CMC preview trace saved: %s (%d samples)"), *Path, SampleRows.Num() - 1);
	}
	else
	{
		UE_LOG(LogMotionWeaverCMCPreview, Error, TEXT("Failed to save CMC preview trace: %s"), *Path);
	}
}
