// Copyright ZhaoZining. All Rights Reserved.

#include "AIAnimationMotionMatchingCharacter.h"
#include "AIAnimationLivePoseComponent.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/InputComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "EnhancedInputSubsystems.h"
#include "Engine/Engine.h"
#include "Engine/LocalPlayer.h"
#include "Engine/SkeletalMesh.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/GameplayCameraComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputCoreTypes.h"
#include "InputMappingContext.h"
#include "HAL/FileManager.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "MotionMatchingInCpp/CommonGameplay/Player/AnimPlayerController.h"
#include "UObject/ConstructorHelpers.h"
#include "UnrealClient.h"

AAIAnimationMotionMatchingCharacter::AAIAnimationMotionMatchingCharacter()
{
	PrimaryActorTick.bCanEverTick = true;
	bGameplayCameraActivated = false;
	GameplayPlayerCamera->bAutoActivate = false;
	GetCapsuleComponent()->InitCapsuleSize(42.0f, 96.0f);
	GetCharacterMovement()->GetNavAgentPropertiesRef().bCanCrouch = true;
	GetMesh()->SetRelativeLocation(FVector(0.0f, 0.0f, -96.0f));
	GetMesh()->SetRelativeRotation(FRotator(0.0f, -90.0f, 0.0f));
	GetMesh()->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
	SpringArm->TargetArmLength = 430.0f;
	SpringArm->bDoCollisionTest = false;
	Camera->bAutoActivate = true;
	LivePose = CreateDefaultSubobject<UAIAnimationLivePoseComponent>(TEXT("LiveModelPose"));
	static ConstructorHelpers::FObjectFinder<USkeletalMesh> MeshAsset(TEXT("/Script/Engine.SkeletalMesh'/MotionMatchingInCpp/Characters/UEFN_Mannequin/Meshes/SKM_UEFN_Mannequin.SKM_UEFN_Mannequin'"));
	if (MeshAsset.Succeeded())
	{
		GetMesh()->SetSkeletalMeshAsset(MeshAsset.Object);
	}
}

void AAIAnimationMotionMatchingCharacter::BeginPlay()
{
	bAutoProbe = FParse::Param(FCommandLine::Get(), TEXT("AIAnimationAutoProbe"));
	bTrajectoryProbe = FParse::Param(FCommandLine::Get(), TEXT("AIAnimationTrajectoryProbe"));
	if ((bAutoProbe || bTrajectoryProbe) && FParse::Param(FCommandLine::Get(), TEXT("AIAnimationAutoProbeWalk")))
	{
		CharacterInputState.bWantsToWalk = true;
	}
	Trace = TEXT("sample,time_s,mode,actor_x_cm,actor_y_cm,actor_z_cm,speed_cmps,crouch,foot_l_x_cm,foot_l_y_cm,foot_l_z_cm,foot_r_x_cm,foot_r_y_cm,foot_r_z_cm,inference_count\n");
	// 原插件 AnimBP 已由准备命令在实体插件副本中插入模型节点，Chooser 的类身份保持不变。
	UClass* LiveAnimClass = LoadClass<UAnimInstance>(nullptr, TEXT("/MotionMatchingInCpp/Blueprints/ABP_PlayerCharacter.ABP_PlayerCharacter_C"));
	if (LiveAnimClass)
	{
		GetMesh()->SetAnimationMode(EAnimationMode::AnimationBlueprint);
		GetMesh()->SetAnimInstanceClass(LiveAnimClass);
	}
	else
	{
		UE_LOG(LogTemp, Error, TEXT("AIAnimationMotionMatching: live AnimBP missing; run preparation commandlet"));
	}
	Super::BeginPlay();
	const auto LogSkeletonBasis = [](const USkeletalMesh* Asset)
	{
		if (!Asset)
		{
			return;
		}
		const FReferenceSkeleton& Skeleton = Asset->GetRefSkeleton();
		const int32 Root = Skeleton.FindBoneIndex(TEXT("root"));
		const int32 Pelvis = Skeleton.FindBoneIndex(TEXT("pelvis"));
		UE_LOG(LogTemp, Display, TEXT("AIAnimationSkeletonBasis: mesh=%s root=%s pelvis=%s"), *Asset->GetPathName(),
			Root == INDEX_NONE ? TEXT("missing") : *Skeleton.GetRefBonePose()[Root].ToString(),
			Pelvis == INDEX_NONE ? TEXT("missing") : *Skeleton.GetRefBonePose()[Pelvis].ToString());
	};
	LogSkeletonBasis(GetMesh()->GetSkeletalMeshAsset());
	GameplayPlayerCamera->Deactivate();
	if (APlayerController* Player = Cast<APlayerController>(GetController()))
	{
		if (ULocalPlayer* LocalPlayer = Player->GetLocalPlayer())
		{
			if (UEnhancedInputLocalPlayerSubsystem* Subsystem = LocalPlayer->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>())
			{
				if (UInputMappingContext* Mapping = LoadObject<UInputMappingContext>(nullptr, TEXT("/MotionMatchingInCpp/Input/IMC_Sandbox.IMC_Sandbox")))
				{
					Subsystem->AddMappingContext(Mapping, 0);
					UE_LOG(LogTemp, Display, TEXT("AIAnimationMotionMatching: installed plugin input mapping with %d bindings"), Mapping->GetMappings().Num());
				}
			}
		}
	}
	UE_LOG(LogTemp, Display, TEXT("AIAnimationMotionMatching: character=%s anim=%s model=%s"), *GetClass()->GetName(), *GetNameSafe(GetMesh()->GetAnimInstance()), LivePose->IsModelReady() ? TEXT("ready") : *LivePose->GetLastError());
}

void AAIAnimationMotionMatchingCharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	TraceRemainderSeconds += FMath::Clamp(DeltaSeconds, 0.0f, 0.1f);
	if (TraceRemainderSeconds >= 1.0f / 30.0f)
	{
		TraceRemainderSeconds -= 1.0f / 30.0f;
		const FVector Position = GetActorLocation();
		const FVector Left = GetMesh()->GetBoneLocation(TEXT("foot_l"));
		const FVector Right = GetMesh()->GetBoneLocation(TEXT("foot_r"));
		Trace += FString::Printf(TEXT("%d,%.4f,%d,%.4f,%.4f,%.4f,%.4f,%d,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%d\n"),
			TraceSample++, GetWorld()->GetTimeSeconds(), LivePose->GetDisplayMode(), Position.X, Position.Y, Position.Z,
			GetVelocity().Size2D(), GetCharacterMovement()->IsCrouching() ? 1 : 0,
			Left.X, Left.Y, Left.Z, Right.X, Right.Y, Right.Z, LivePose->GetInferenceCount());
	}
	if (bAutoProbe || bTrajectoryProbe)
	{
		ProbeSeconds += DeltaSeconds;
		if (bTrajectoryProbe)
		{
			if (ProbeSeconds < 2.0f)
			{
				AddMovementInput(FVector::ForwardVector);
			}
			else if (ProbeSeconds < 4.0f)
			{
				AddMovementInput(FVector::RightVector);
			}
			LivePose->SetDisplayMode(1);
		}
		else if (ProbeSeconds < 7.5f)
		{
			AddMovementInput(GetActorForwardVector());
		}
		if (!bTrajectoryProbe)
		{
			LivePose->SetDisplayMode(ProbeSeconds < 2.0f ? 0 : ProbeSeconds < 4.0f ? 1 : 2);
		}
		if (!bTrajectoryProbe && ProbeSeconds >= 6.0f && !bProbeCrouched)
		{
			Crouch();
			bProbeCrouched = true;
		}
		const int32 Second = FMath::FloorToInt(ProbeSeconds);
		if (Second != LastProbeSecond)
		{
			LastProbeSecond = Second;
			const FVector Left = GetMesh()->GetBoneLocation(TEXT("foot_l"));
			const FVector Right = GetMesh()->GetBoneLocation(TEXT("foot_r"));
			const FVector ShoulderRight = GetMesh()->GetBoneLocation(TEXT("upperarm_r"))
				- GetMesh()->GetBoneLocation(TEXT("upperarm_l"));
			const FVector BodyUp = GetMesh()->GetBoneLocation(TEXT("spine_03"))
				- GetMesh()->GetBoneLocation(TEXT("pelvis"));
			const FVector BodyForward = FVector::CrossProduct(ShoulderRight, BodyUp).GetSafeNormal2D();
			UE_LOG(LogTemp, Display, TEXT("AIAnimationAutoProbe: t=%d mode=%d x=%.1f y=%.1f speed=%.1f actor_yaw=%.1f velocity_yaw=%.1f body_yaw=%.1f crouch=%d left_z=%.1f right_z=%.1f inference=%d"),
				Second, LivePose->GetDisplayMode(), GetActorLocation().X, GetActorLocation().Y, GetVelocity().Size2D(),
				GetActorRotation().Yaw, GetVelocity().ToOrientationRotator().Yaw, BodyForward.ToOrientationRotator().Yaw,
				GetCharacterMovement()->IsCrouching() ? 1 : 0, Left.Z, Right.Z, LivePose->GetInferenceCount());
			if (Second == 1 || Second == 3 || Second == 5 || Second == 7)
			{
				const FString ImageName = bTrajectoryProbe
					? FString::Printf(TEXT("AIAnimation/MotionMatchingTrajectoryProbe_%d.png"), Second)
					: FString::Printf(TEXT("AIAnimation/MotionMatchingProbe_%d.png"), Second);
				const FString ImagePath = FPaths::ProjectSavedDir() / ImageName;
				IFileManager::Get().MakeDirectory(*FPaths::GetPath(ImagePath), true);
				FScreenshotRequest::RequestScreenshot(ImagePath, false, false);
			}
		}
		if (ProbeSeconds >= (bTrajectoryProbe ? 6.0f : 8.0f))
		{
			QuitTest();
		}
	}
	if (!GEngine)
	{
		return;
	}
	const TCHAR* Mode = LivePose->GetDisplayMode() == 0 ? TEXT("MOTION MATCHING")
		: LivePose->GetDisplayMode() == 1 ? TEXT("MODEL CONTROL - QUALITY NOT PASSED")
			: TEXT("MODEL SPEED/PHASE - REJECTED PILOT");
	GEngine->AddOnScreenDebugMessage(9200, 0.0f, LivePose->IsModelReady() ? FColor::Green : FColor::Red,
		FString::Printf(TEXT("MotionMatchingInCpp + AIAnimation | %s | %.0f cm/s | NNE %.2f ms | #%d"), Mode,
			GetVelocity().Size2D(), LivePose->GetLastInferenceMs(), LivePose->GetInferenceCount()));
	GEngine->AddOnScreenDebugMessage(9201, 0.0f, FColor::White,
		TEXT("WASD 移动 鼠标转向 Shift 冲刺 C 蹲伏 | 1 原运动匹配 2 对照模型 3 速度模型 | R 重置 Esc 退出"));
	if (LivePose->GetDisplayMode() != 0)
	{
		GEngine->AddOnScreenDebugMessage(9203, 0.0f, FColor::Orange,
			TEXT("实验模型仍有方向偏差和脚滑；按 1 返回原 Motion Matching"));
	}
	if (GetCharacterMovement()->IsCrouching())
	{
		GEngine->AddOnScreenDebugMessage(9202, 0.0f, FColor::Yellow, TEXT("蹲伏由插件 CMC/AnimBP 负责；当前模型没有 Stance 输入，自动回退原动画"));
	}
}

void AAIAnimationMotionMatchingCharacter::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	const FString TracePath = FPaths::ProjectSavedDir() / TEXT("AIAnimation/MotionMatchingTrace.csv");
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(TracePath), true);
	FFileHelper::SaveStringToFile(Trace, *TracePath);
	UE_LOG(LogTemp, Display, TEXT("AIAnimationMotionMatching: trace=%s samples=%d"), *TracePath, TraceSample);
	Super::EndPlay(EndPlayReason);
}

void AAIAnimationMotionMatchingCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);
	PlayerInputComponent->BindKey(EKeys::One, IE_Pressed, this, &AAIAnimationMotionMatchingCharacter::ShowMotionMatching);
	PlayerInputComponent->BindKey(EKeys::Two, IE_Pressed, this, &AAIAnimationMotionMatchingCharacter::ShowControlModel);
	PlayerInputComponent->BindKey(EKeys::Three, IE_Pressed, this, &AAIAnimationMotionMatchingCharacter::ShowSpeedPhaseModel);
	PlayerInputComponent->BindKey(EKeys::R, IE_Pressed, this, &AAIAnimationMotionMatchingCharacter::ResetTest);
	PlayerInputComponent->BindKey(EKeys::Escape, IE_Pressed, this, &AAIAnimationMotionMatchingCharacter::QuitTest);
}

void AAIAnimationMotionMatchingCharacter::ShowMotionMatching() { LivePose->SetDisplayMode(0); }
void AAIAnimationMotionMatchingCharacter::ShowControlModel() { LivePose->SetDisplayMode(1); }
void AAIAnimationMotionMatchingCharacter::ShowSpeedPhaseModel() { LivePose->SetDisplayMode(2); }

void AAIAnimationMotionMatchingCharacter::ResetTest()
{
	GetCharacterMovement()->StopMovementImmediately();
	SetActorLocationAndRotation(FVector(0.0f, 0.0f, 96.0f), FRotator::ZeroRotator);
	LivePose->ResetModel();
}

void AAIAnimationMotionMatchingCharacter::QuitTest()
{
	if (APlayerController* Player = Cast<APlayerController>(GetController()))
	{
		Player->ConsoleCommand(TEXT("quit"), true);
	}
}

AAIAnimationMotionMatchingGameMode::AAIAnimationMotionMatchingGameMode()
{
	DefaultPawnClass = AAIAnimationMotionMatchingCharacter::StaticClass();
	PlayerControllerClass = AAnimPlayerController::StaticClass();
}
