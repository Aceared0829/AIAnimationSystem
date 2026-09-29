// Copyright ZhaoZining. All Rights Reserved.

// 在真实 CharacterMovementComponent 上施加脚本输入并保存胶囊轨迹，供离线条件姿态实验读取。
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "Engine/World.h"
#include "Misc/AutomationTest.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Tests/AutomationCommon.h"

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAIAnimationCMCRootCaptureTest, "AIAnimation.Lab.CMCRootCapture", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FAIAnimationCMCRootCaptureTest::RunTest(const FString& Parameters)
{
	FTestWorldWrapper WorldWrapper;
	if (!TestTrue(TEXT("创建 Game 测试 World"), WorldWrapper.CreateTestWorld(EWorldType::Game)))
	{
		return false;
	}
	UWorld* World = WorldWrapper.GetTestWorld();
	if (!TestNotNull(TEXT("测试 World 有效"), World))
	{
		return false;
	}

	AActor* Floor = World->SpawnActor<AActor>();
	if (!TestNotNull(TEXT("创建碰撞地面"), Floor))
	{
		return false;
	}
	UBoxComponent* FloorBox = NewObject<UBoxComponent>(Floor);
	FloorBox->SetBoxExtent(FVector(5000.0, 5000.0, 50.0));
	FloorBox->SetCollisionProfileName(TEXT("BlockAll"));
	Floor->SetRootComponent(FloorBox);
	FloorBox->RegisterComponent();
	Floor->SetActorLocation(FVector(0.0, 0.0, -50.0));
	if (!TestTrue(TEXT("World 开始 Play"), WorldWrapper.BeginPlayInTestWorld()))
	{
		return false;
	}

	FString Csv = TEXT("scenario,frame,input_x,input_y,capsule_x_cm,capsule_y_cm,capsule_z_cm,capsule_half_height_cm,quat_x,quat_y,quat_z,quat_w,velocity_x_cmps,velocity_y_cmps,velocity_z_cmps,movement_mode,is_crouched\n");
	const FString ScenarioNames[] = { TEXT("walk"), TEXT("run"), TEXT("crouch") };
	const double WalkSpeeds[] = { 140.0, 400.0, 80.0 };
	for (int32 ScenarioIndex = 0; ScenarioIndex < 3; ++ScenarioIndex)
	{
		ACharacter* Character = World->SpawnActor<ACharacter>(FVector(0.0, ScenarioIndex * 350.0, 96.0), FRotator::ZeroRotator);
		if (!TestNotNull(TEXT("创建 Character"), Character))
		{
			return false;
		}
		UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
		Movement->bRunPhysicsWithNoController = true;
		Movement->bOrientRotationToMovement = true;
		Movement->RotationRate = FRotator(0.0, 720.0, 0.0);
		Movement->MaxWalkSpeed = WalkSpeeds[ScenarioIndex];
		Movement->MaxWalkSpeedCrouched = 80.0;
		Movement->GetNavAgentPropertiesRef().bCanCrouch = true;
		Movement->SetMovementMode(MOVE_Walking);
		const FVector Start = Character->GetActorLocation();
		for (int32 Frame = 0; Frame < 96; ++Frame)
		{
			const FVector Input = Frame < 48 ? FVector::ForwardVector : Frame < 72 ? FVector::RightVector : FVector::ZeroVector;
			if (ScenarioIndex == 2 && Frame == 48)
			{
				Character->Crouch();
			}
			if (!Input.IsZero())
			{
				Character->AddMovementInput(Input, 1.0, true);
			}
			if (!WorldWrapper.TickTestWorld(1.0f / 30.0f))
			{
				WorldWrapper.ForwardErrorMessages(this);
				return false;
			}
			const FVector Location = Character->GetActorLocation();
			const double HalfHeight = Character->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
			const FQuat Rotation = Character->GetActorQuat();
			const FVector Velocity = Movement->Velocity;
			Csv += FString::Printf(TEXT("%s,%d,%.6f,%.6f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%d,%d\n"),
				*ScenarioNames[ScenarioIndex], Frame, Input.X, Input.Y, Location.X, Location.Y, Location.Z, HalfHeight,
				Rotation.X, Rotation.Y, Rotation.Z, Rotation.W, Velocity.X, Velocity.Y, Velocity.Z,
				static_cast<int32>(Movement->MovementMode), Character->bIsCrouched ? 1 : 0);
		}
		TestTrue(TEXT("CMC 产生实际胶囊位移"), FVector::Dist2D(Start, Character->GetActorLocation()) > 100.0);
		Character->Destroy();
	}

	FString OutputPath = FPlatformMisc::GetEnvironmentVariable(TEXT("AIANIMATION_CMC_TRACE_PATH"));
	if (OutputPath.IsEmpty())
	{
		OutputPath = FPaths::ProjectSavedDir() / TEXT("AIAnimation/CMCRootCapture.csv");
	}
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(OutputPath), true);
	TestTrue(TEXT("保存 CMC 胶囊轨迹"), FFileHelper::SaveStringToFile(Csv, *OutputPath));
	WorldWrapper.ForwardErrorMessages(this);
	return !HasAnyErrors();
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAIAnimationSteadyCMCRootCaptureTest, "AIAnimation.Lab.SteadyCMCRootCapture", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FAIAnimationSteadyCMCRootCaptureTest::RunTest(const FString& Parameters)
{
	FTestWorldWrapper WorldWrapper;
	if (!TestTrue(TEXT("创建匀速 CMC 测试 World"), WorldWrapper.CreateTestWorld(EWorldType::Game)))
	{
		return false;
	}
	UWorld* World = WorldWrapper.GetTestWorld();
	AActor* Floor = World->SpawnActor<AActor>();
	UBoxComponent* FloorBox = NewObject<UBoxComponent>(Floor);
	FloorBox->SetBoxExtent(FVector(5000.0, 5000.0, 50.0));
	FloorBox->SetCollisionProfileName(TEXT("BlockAll"));
	Floor->SetRootComponent(FloorBox);
	FloorBox->RegisterComponent();
	Floor->SetActorLocation(FVector(0.0, 0.0, -50.0));
	if (!TestTrue(TEXT("匀速 CMC World 开始 Play"), WorldWrapper.BeginPlayInTestWorld()))
	{
		return false;
	}

	// 速度和方向与实验中预先选定的封版片段对应；Run 仅用训练分区片段诊断。先暖机以排除启动加速造成的历史条件错配。
	const FString ScenarioNames[] = { TEXT("walk"), TEXT("run"), TEXT("crouch") };
	const FVector Directions[] = { FVector(0.0, -1.0, 0.0), FVector(1.0, 0.0, 0.0), FVector(1.0, 1.0, 0.0).GetSafeNormal() };
	const double Speeds[] = { 165.0, 375.0, 225.0 };
	FString Csv = TEXT("scenario,frame,input_x,input_y,capsule_x_cm,capsule_y_cm,capsule_z_cm,capsule_half_height_cm,quat_x,quat_y,quat_z,quat_w,velocity_x_cmps,velocity_y_cmps,velocity_z_cmps,movement_mode,is_crouched\n");
	for (int32 ScenarioIndex = 0; ScenarioIndex < 3; ++ScenarioIndex)
	{
		ACharacter* Character = World->SpawnActor<ACharacter>(FVector(0.0, ScenarioIndex * 350.0, 96.0), FRotator::ZeroRotator);
		if (!TestNotNull(TEXT("创建匀速 CMC Character"), Character))
		{
			return false;
		}
		UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
		Movement->bRunPhysicsWithNoController = true;
		Movement->bOrientRotationToMovement = false;
		Movement->MaxWalkSpeed = Speeds[ScenarioIndex];
		Movement->MaxWalkSpeedCrouched = Speeds[ScenarioIndex];
		Movement->GetNavAgentPropertiesRef().bCanCrouch = true;
		Movement->SetMovementMode(MOVE_Walking);
		if (ScenarioIndex == 2)
		{
			Character->Crouch();
		}
		for (int32 Frame = -60; Frame < 96; ++Frame)
		{
			Character->AddMovementInput(Directions[ScenarioIndex], 1.0, true);
			if (!WorldWrapper.TickTestWorld(1.0f / 30.0f))
			{
				WorldWrapper.ForwardErrorMessages(this);
				return false;
			}
			if (Frame < 0)
			{
				continue;
			}
			const FVector Location = Character->GetActorLocation();
			const double HalfHeight = Character->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
			const FQuat Rotation = Character->GetActorQuat();
			const FVector Velocity = Movement->Velocity;
			Csv += FString::Printf(TEXT("%s,%d,%.6f,%.6f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%d,%d\n"),
				*ScenarioNames[ScenarioIndex], Frame, Directions[ScenarioIndex].X, Directions[ScenarioIndex].Y,
				Location.X, Location.Y, Location.Z, HalfHeight, Rotation.X, Rotation.Y, Rotation.Z, Rotation.W,
				Velocity.X, Velocity.Y, Velocity.Z, static_cast<int32>(Movement->MovementMode), Character->bIsCrouched ? 1 : 0);
		}
		TestTrue(TEXT("匀速 CMC 始终沿地面移动"), Movement->MovementMode == MOVE_Walking);
		if (ScenarioIndex == 2)
		{
			TestTrue(TEXT("蹲姿场景始终获准蹲下"), Character->bIsCrouched);
		}
		Character->Destroy();
	}
	FString OutputPath = FPlatformMisc::GetEnvironmentVariable(TEXT("AIANIMATION_CMC_MATCHED_TRACE_PATH"));
	if (OutputPath.IsEmpty())
	{
		OutputPath = FPaths::ProjectSavedDir() / TEXT("AIAnimation/SteadyCMCRootCapture.csv");
	}
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(OutputPath), true);
	TestTrue(TEXT("保存匀速 CMC 轨迹"), FFileHelper::SaveStringToFile(Csv, *OutputPath));
	WorldWrapper.ForwardErrorMessages(this);
	return !HasAnyErrors();
}
#endif
