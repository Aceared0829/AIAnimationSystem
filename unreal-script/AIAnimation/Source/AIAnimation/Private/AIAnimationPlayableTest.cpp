// Copyright ZhaoZining. All Rights Reserved.

/**
 * @file AIAnimationPlayableTest.cpp
 * @brief 实现本地玩家 CMC 位移、因果 Root 规划、NNE 姿态生成和可见诊断。
 *
 * 只读封装导出的训练契约；模型输出不驱动胶囊，四帧后重新规划以暴露在线接缝。
 */

#include "AIAnimationPlayableTest.h"
#include "AIAnimationLivePoseComponent.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/InputComponent.h"
#include "Components/LightComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/PoseableMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "DrawDebugHelpers.h"
#include "Engine/DirectionalLight.h"
#include "Engine/Engine.h"
#include "Engine/PointLight.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMeshActor.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "InputCoreTypes.h"
#include "Materials/MaterialInterface.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "NNE.h"
#include "NNEModelData.h"
#include "NNERuntimeCPU.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/StrongObjectPtr.h"

namespace
{
	constexpr int32 NumFrames = 24;
	constexpr int32 NumBones = 79;
	constexpr int32 PoseValues = NumBones * 9;
	constexpr int32 RootValues = 7;
	constexpr int32 HistoryValues = PoseValues + RootValues;
	constexpr float SampleSeconds = 1.0f / 30.0f;

	struct FPlayableBone
	{
		FName Name;
		int32 ParentIndex = INDEX_NONE;
		int32 MeshIndex = INDEX_NONE;
		FQuat ReferenceRotation;
	};

	struct FPlayableModel
	{
		TStrongObjectPtr<UNNEModelData> ModelData;
		TSharedPtr<UE::NNE::IModelCPU> Model;
		TSharedPtr<UE::NNE::IModelInstanceCPU> Instance;
	};

	bool LoadFloatFile(const FString& Path, int32 Count, TArray<float>& OutValues)
	{
		TArray<uint8> Bytes;
		if (!FFileHelper::LoadFileToArray(Bytes, *Path) || Bytes.Num() != Count * sizeof(float))
		{
			return false;
		}
		OutValues.SetNumUninitialized(Count);
		FMemory::Memcpy(OutValues.GetData(), Bytes.GetData(), Bytes.Num());
		for (float Value : OutValues)
		{
			if (!FMath::IsFinite(Value))
			{
				return false;
			}
		}
		return true;
	}

	FVector UnrealToData(const FVector& Value)
	{
		return FVector(-Value.Y, Value.Z, Value.X);
	}

	FVector DataToUnreal(const FVector& Value)
	{
		return FVector(Value.Z, -Value.X, Value.Y);
	}

	FQuat UnrealToData(const FQuat& Value)
	{
		return FQuat(Value.Y, -Value.Z, -Value.X, Value.W).GetNormalized();
	}

	FQuat DataToUnreal(const FQuat& Value)
	{
		return FQuat(-Value.Z, Value.X, -Value.Y, Value.W).GetNormalized();
	}

	void WriteLocalRoot(const FTransform& Root, const FTransform& Origin, float* OutValues)
	{
		const FQuat OriginRotation = Origin.GetRotation();
		const FVector LocalPosition = OriginRotation.Inverse().RotateVector(Root.GetLocation() - Origin.GetLocation()) / 100.0;
		const FQuat LocalRotation = (OriginRotation.Inverse() * Root.GetRotation()).GetNormalized();
		const FVector Position = UnrealToData(LocalPosition);
		const FQuat Rotation = UnrealToData(LocalRotation);
		OutValues[0] = Position.X;
		OutValues[1] = Position.Y;
		OutValues[2] = Position.Z;
		OutValues[3] = Rotation.X;
		OutValues[4] = Rotation.Y;
		OutValues[5] = Rotation.Z;
		OutValues[6] = Rotation.W;
	}

	FQuat DecodeRotation(const float* Values)
	{
		FVector First(Values[0], Values[2], Values[4]);
		FVector Second(Values[1], Values[3], Values[5]);
		First = First.GetSafeNormal();
		Second = (Second - First * FVector::DotProduct(First, Second)).GetSafeNormal();
		if (First.IsNearlyZero() || Second.IsNearlyZero())
		{
			return FQuat::Identity;
		}
		const FVector Third = FVector::CrossProduct(First, Second);
		FMatrix Matrix = FMatrix::Identity;
		Matrix.SetAxes(&First, &Second, &Third);
		return FQuat(Matrix).GetNormalized();
	}
}

struct FAIAnimationPlayableRuntime
{
	FPlayableModel Models[2];
	TArray<FPlayableBone> Bones;
	TArray<float> Mean;
	TArray<float> Std;
	TArray<float> SeedPose;
	TArray<float> PoseHistory;
	TArray<FTransform> RootHistory;
	TArray<float> HistoryInput;
	TArray<float> RootPlanInput;
	TArray<float> ReferenceInput;
	TArray<float> MaskInput;
	TArray<float> Generated;
	FString Error;
	FString Trace;
	float LastInferenceMs = 0.0f;
	int32 GeneratedFrame = 4;
	int32 NumInference = 0;
	int32 NumSamples = 0;
	USkeletalMesh* Mesh = nullptr;

	bool Initialize(const FString& Bundle, USkeletalMesh& InMesh)
	{
		Mesh = &InMesh;
		if (!LoadFloatFile(Bundle / TEXT("mean.f32"), NumBones * 3, Mean)
			|| !LoadFloatFile(Bundle / TEXT("std.f32"), NumBones * 3, Std)
			|| !LoadFloatFile(Bundle / TEXT("seed_pose.f32"), NumFrames * PoseValues, SeedPose))
		{
			Error = TEXT("缺少训练统计量或 Idle 种子姿态");
			return false;
		}
		FString Json;
		TSharedPtr<FJsonObject> Skeleton;
		if (!FFileHelper::LoadFileToString(Json, *(Bundle / TEXT("skeleton.json")))
			|| !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Skeleton) || !Skeleton.IsValid())
		{
			Error = TEXT("无法读取骨架契约");
			return false;
		}
		const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
		if (!Skeleton->TryGetArrayField(TEXT("bones"), Values) || Values->Num() != NumBones)
		{
			Error = TEXT("骨架数量不是 79");
			return false;
		}
		const FReferenceSkeleton& ReferenceSkeleton = InMesh.GetRefSkeleton();
		for (const TSharedPtr<FJsonValue>& Value : *Values)
		{
			const TSharedPtr<FJsonObject> Object = Value->AsObject();
			FPlayableBone Bone;
			FString Name;
			const TArray<TSharedPtr<FJsonValue>>* Quaternion = nullptr;
			if (!Object.IsValid() || !Object->TryGetStringField(TEXT("name"), Name)
				|| !Object->TryGetNumberField(TEXT("parent"), Bone.ParentIndex)
				|| !Object->TryGetArrayField(TEXT("rotation"), Quaternion) || Quaternion->Num() != 4)
			{
				Error = TEXT("骨架字段不完整");
				return false;
			}
			Bone.Name = FName(Name);
			Bone.MeshIndex = ReferenceSkeleton.FindBoneIndex(Bone.Name);
			Bone.ReferenceRotation = FQuat((*Quaternion)[0]->AsNumber(), (*Quaternion)[1]->AsNumber(), (*Quaternion)[2]->AsNumber(), (*Quaternion)[3]->AsNumber());
			if (Bone.MeshIndex == INDEX_NONE || !Bone.ReferenceRotation.IsNormalized()
				|| (Bone.ParentIndex != INDEX_NONE && (Bone.ParentIndex < 0 || Bone.ParentIndex >= Bones.Num()
					|| ReferenceSkeleton.GetParentIndex(Bone.MeshIndex) != Bones[Bone.ParentIndex].MeshIndex)))
			{
				Error = FString::Printf(TEXT("骨骼 %s 与网格不匹配"), *Name);
				return false;
			}
			Bones.Add(Bone);
		}
		const FString Names[2] = { TEXT("model_control.onnx"), TEXT("model_speed_phase.onnx") };
		for (int32 Index = 0; Index < 2; ++Index)
		{
			if (!LoadModel(Bundle / Names[Index], Models[Index]))
			{
				Error = FString::Printf(TEXT("NNE 无法加载 %s"), *Names[Index]);
				return false;
			}
		}
		HistoryInput.SetNumZeroed(NumFrames * HistoryValues);
		RootPlanInput.SetNumZeroed(NumFrames * RootValues);
		ReferenceInput.SetNumZeroed(NumFrames * PoseValues);
		MaskInput.SetNumZeroed(NumFrames);
		Generated.SetNumZeroed(NumFrames * PoseValues);
		Trace = TEXT("sample,model,actor_x_cm,actor_y_cm,actor_z_cm,velocity_x_cmps,velocity_y_cmps,velocity_z_cmps,is_crouched,foot_l_x_cm,foot_l_y_cm,foot_l_z_cm,foot_r_x_cm,foot_r_y_cm,foot_r_z_cm,inference_ms\n");
		return true;
	}

	bool LoadModel(const FString& Path, FPlayableModel& OutModel)
	{
		TArray<uint8> Bytes;
		if (!FFileHelper::LoadFileToArray(Bytes, *Path))
		{
			return false;
		}
		OutModel.ModelData.Reset(NewObject<UNNEModelData>());
		OutModel.ModelData->Init(TEXT("onnx"), MakeArrayView(Bytes));
		OutModel.ModelData->SetTargetRuntimes({ TEXT("NNERuntimeORTCpu") });
		TWeakInterfacePtr<INNERuntimeCPU> Runtime = UE::NNE::GetRuntime<INNERuntimeCPU>(TEXT("NNERuntimeORTCpu"));
		if (!Runtime.IsValid() || Runtime->CanCreateModelCPU(OutModel.ModelData.Get()) != UE::NNE::EResultStatus::Ok)
		{
			return false;
		}
		OutModel.Model = Runtime->CreateModelCPU(OutModel.ModelData.Get());
		OutModel.Instance = OutModel.Model ? OutModel.Model->CreateModelInstanceCPU() : nullptr;
		if (!OutModel.Instance || OutModel.Instance->GetInputTensorDescs().Num() != 4 || OutModel.Instance->GetOutputTensorDescs().Num() != 1)
		{
			return false;
		}
		const TArray<UE::NNE::FTensorShape> Shapes = {
			UE::NNE::FTensorShape::Make({ 1u, 24u, 718u }), UE::NNE::FTensorShape::Make({ 1u, 24u, 7u }),
			UE::NNE::FTensorShape::Make({ 1u, 24u, 711u }), UE::NNE::FTensorShape::Make({ 1u, 24u, 1u })
		};
		return OutModel.Instance->SetInputTensorShapes(Shapes) == UE::NNE::EResultStatus::Ok
			&& OutModel.Instance->GetOutputTensorShapes().Num() == 1
			&& OutModel.Instance->GetOutputTensorShapes()[0].Volume() == NumFrames * PoseValues;
	}

	void Reset(const FTransform& Root)
	{
		PoseHistory = SeedPose;
		RootHistory.Init(Root, NumFrames);
		GeneratedFrame = 4;
		LastInferenceMs = 0.0f;
		Error.Reset();
	}

	bool Predict(int32 ModelIndex, const FTransform& CurrentRoot, const FVector& VelocityCmps,
		const TArray<FTransform>* PlannedRoots = nullptr)
	{
		if (PlannedRoots && PlannedRoots->Num() != NumFrames)
		{
			Error = TEXT("Root 轨迹帧数与模型窗口不一致");
			return false;
		}
		const FTransform& Origin = RootHistory.Last();
		FVector PlanarVelocity = VelocityCmps;
		PlanarVelocity.Z = 0.0f;
		for (int32 Frame = 0; Frame < NumFrames; ++Frame)
		{
			float* Row = HistoryInput.GetData() + Frame * HistoryValues;
			FMemory::Memcpy(Row, PoseHistory.GetData() + Frame * PoseValues, PoseValues * sizeof(float));
			WriteLocalRoot(RootHistory[Frame], Origin, Row + PoseValues);
			const FVector Position = CurrentRoot.GetLocation() + PlanarVelocity * (float(Frame) * SampleSeconds);
			const FTransform Planned = PlannedRoots ? (*PlannedRoots)[Frame] : FTransform(CurrentRoot.GetRotation(), Position);
			WriteLocalRoot(Planned, Origin, RootPlanInput.GetData() + Frame * RootValues);
		}
		Generated.SetNumZeroed(NumFrames * PoseValues);
		const TArray<UE::NNE::FTensorBindingCPU> Inputs = {
			{ HistoryInput.GetData(), uint64(HistoryInput.Num()) * sizeof(float) },
			{ RootPlanInput.GetData(), uint64(RootPlanInput.Num()) * sizeof(float) },
			{ ReferenceInput.GetData(), uint64(ReferenceInput.Num()) * sizeof(float) },
			{ MaskInput.GetData(), uint64(MaskInput.Num()) * sizeof(float) }
		};
		const UE::NNE::FTensorBindingCPU Output { Generated.GetData(), uint64(Generated.Num()) * sizeof(float) };
		const double Started = FPlatformTime::Seconds();
		const UE::NNE::EResultStatus Status = Models[ModelIndex].Instance->RunSync(Inputs, MakeArrayView(&Output, 1));
		LastInferenceMs = float((FPlatformTime::Seconds() - Started) * 1000.0);
		if (Status != UE::NNE::EResultStatus::Ok)
		{
			Error = TEXT("NNE 推理失败");
			return false;
		}
		for (float Value : Generated)
		{
			if (!FMath::IsFinite(Value))
			{
				Error = TEXT("NNE 输出非有限值");
				return false;
			}
		}
		GeneratedFrame = 0;
		++NumInference;
		if (NumInference <= 2 || NumInference % 10 == 0)
		{
			const FTransform FinalRoot = PlannedRoots ? PlannedRoots->Last()
				: FTransform(CurrentRoot.GetRotation(), CurrentRoot.GetLocation() + PlanarVelocity * ((NumFrames - 1) * SampleSeconds));
			const FVector LocalVelocity = Origin.GetRotation().Inverse().RotateVector(PlanarVelocity);
			const FVector FutureLocalDelta = Origin.GetRotation().Inverse().RotateVector(FinalRoot.GetLocation() - Origin.GetLocation());
			UE_LOG(LogTemp, Display, TEXT("AIAnimationRootPlan: model=%d inference=%d local_velocity_cmps=%s future_23_local_cm=%s root_yaw=%.1f future_yaw=%.1f"),
				ModelIndex, NumInference, *LocalVelocity.ToString(), *FutureLocalDelta.ToString(),
				CurrentRoot.Rotator().Yaw, FinalRoot.Rotator().Yaw);
		}
		return true;
	}

	bool ApplyPose(UPoseableMeshComponent& Skin, const float* Pose) const
	{
		TArray<FTransform, TInlineAllocator<79>> Components;
		Components.SetNum(NumBones);
		Skin.BoneSpaceTransforms = Mesh->GetRefSkeleton().GetRefBonePose();
		for (int32 Index = 0; Index < NumBones; ++Index)
		{
			const int32 Base = Index * 9;
			const FVector DataPosition(Pose[Base] * Std[Index * 3] + Mean[Index * 3],
				Pose[Base + 1] * Std[Index * 3 + 1] + Mean[Index * 3 + 1], Pose[Base + 2] * Std[Index * 3 + 2] + Mean[Index * 3 + 2]);
			const FQuat Rotation = DataToUnreal(DecodeRotation(Pose + Base + 3)) * Bones[Index].ReferenceRotation;
			const FTransform Component(Rotation.GetNormalized(), DataToUnreal(DataPosition) * 100.0);
			if (Component.ContainsNaN())
			{
				return false;
			}
			Components[Index] = Component;
			const FTransform Parent = Bones[Index].ParentIndex == INDEX_NONE ? FTransform::Identity : Components[Bones[Index].ParentIndex];
			Skin.BoneSpaceTransforms[Bones[Index].MeshIndex] = Component.GetRelativeTransform(Parent);
		}
		Skin.MarkRefreshTransformDirty();
		return true;
	}

	bool BuildLocalPose(const float* Pose, TArray<FTransform>& OutLocalPose) const
	{
		TArray<FTransform, TInlineAllocator<79>> Components;
		Components.SetNum(NumBones);
		OutLocalPose.SetNum(NumBones);
		for (int32 Index = 0; Index < NumBones; ++Index)
		{
			const int32 Base = Index * 9;
			const FVector DataPosition(Pose[Base] * Std[Index * 3] + Mean[Index * 3],
				Pose[Base + 1] * Std[Index * 3 + 1] + Mean[Index * 3 + 1], Pose[Base + 2] * Std[Index * 3 + 2] + Mean[Index * 3 + 2]);
			const FQuat Rotation = DataToUnreal(DecodeRotation(Pose + Base + 3)) * Bones[Index].ReferenceRotation;
			const FTransform Component(Rotation.GetNormalized(), DataToUnreal(DataPosition) * 100.0);
			if (Component.ContainsNaN())
			{
				OutLocalPose.Reset();
				return false;
			}
			Components[Index] = Component;
			const FTransform Parent = Bones[Index].ParentIndex == INDEX_NONE ? FTransform::Identity : Components[Bones[Index].ParentIndex];
			OutLocalPose[Index] = Component.GetRelativeTransform(Parent);
		}
		return true;
	}

	void AppendHistory(const FTransform& Root)
	{
		FMemory::Memmove(PoseHistory.GetData(), PoseHistory.GetData() + PoseValues, (NumFrames - 1) * PoseValues * sizeof(float));
		FMemory::Memcpy(PoseHistory.GetData() + (NumFrames - 1) * PoseValues, Generated.GetData() + GeneratedFrame * PoseValues, PoseValues * sizeof(float));
		RootHistory.RemoveAt(0);
		RootHistory.Add(Root);
		++GeneratedFrame;
	}
};

UAIAnimationLivePoseComponent::UAIAnimationLivePoseComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
}

UAIAnimationLivePoseComponent::~UAIAnimationLivePoseComponent()
{
	delete Runtime;
}

void UAIAnimationLivePoseComponent::BeginPlay()
{
	Super::BeginPlay();
	ACharacter* Character = Cast<ACharacter>(GetOwner());
	USkeletalMesh* SkeletalAsset = Character && Character->GetMesh() ? Character->GetMesh()->GetSkeletalMeshAsset() : nullptr;
	if (!Character || !SkeletalAsset || !Character->GetCharacterMovement())
	{
		StartupError = TEXT("角色没有 CMC 或 UEFN 骨架");
		return;
	}
	PrimaryComponentTick.AddPrerequisite(Character->GetCharacterMovement(), Character->GetCharacterMovement()->PrimaryComponentTick);
	const FString Bundle = FPlatformMisc::GetEnvironmentVariable(TEXT("AIANIMATION_PLAYABLE_BUNDLE"));
	Runtime = new FAIAnimationPlayableRuntime();
	if (Bundle.IsEmpty() || !Runtime->Initialize(Bundle, *SkeletalAsset))
	{
		StartupError = Bundle.IsEmpty() ? TEXT("未设置 AIANIMATION_PLAYABLE_BUNDLE") : Runtime->Error;
		UE_LOG(LogTemp, Error, TEXT("AIAnimationLivePose: %s"), *StartupError);
		return;
	}
	for (const FPlayableBone& Bone : Runtime->Bones)
	{
		BoneNames.Add(Bone.Name);
	}
	ResetModel();
	UE_LOG(LogTemp, Display, TEXT("AIAnimationLivePose: model ready; mesh=%s"), *SkeletalAsset->GetName());
}

void UAIAnimationLivePoseComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	delete Runtime;
	Runtime = nullptr;
	Super::EndPlay(EndPlayReason);
}

void UAIAnimationLivePoseComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	if (!IsModelReady())
	{
		return;
	}
	const ACharacter* Character = Cast<ACharacter>(GetOwner());
	const bool bModelEligible = Character && Character->GetCharacterMovement()->IsMovingOnGround()
		&& !Character->GetCharacterMovement()->IsCrouching();
	if (!bModelEligible)
	{
		bWasModelEligible = false;
		return;
	}
	if (!bWasModelEligible)
	{
		ResetModel();
		bWasModelEligible = true;
	}
	SampleRemainderSeconds += FMath::Clamp(DeltaTime, 0.0f, 0.1f);
	for (int32 Steps = 0; SampleRemainderSeconds >= SampleSeconds && Steps < 4; ++Steps)
	{
		SampleRemainderSeconds -= SampleSeconds;
		StepModel();
	}
}

void UAIAnimationLivePoseComponent::SetDisplayMode(int32 NewMode)
{
	if (NewMode < 0 || NewMode > 2 || NewMode == DisplayMode)
	{
		return;
	}
	DisplayMode = NewMode;
}

void UAIAnimationLivePoseComponent::ResetModel()
{
	ACharacter* Character = Cast<ACharacter>(GetOwner());
	if (!Runtime || !StartupError.IsEmpty() || !Character)
	{
		return;
	}
	const float HalfHeight = Character->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	const FTransform GroundRoot(Character->GetActorQuat(), Character->GetActorLocation() - FVector(0.0f, 0.0f, HalfHeight));
	Runtime->Reset(GroundRoot);
	bHasPose = Runtime->BuildLocalPose(Runtime->SeedPose.GetData() + (NumFrames - 1) * PoseValues, LatestLocalPose);
	SampleRemainderSeconds = 0.0f;
}

void UAIAnimationLivePoseComponent::StepModel()
{
	ACharacter* Character = Cast<ACharacter>(GetOwner());
	if (!Character || !Runtime)
	{
		return;
	}
	const float HalfHeight = Character->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	const FTransform GroundRoot(Character->GetActorQuat(), Character->GetActorLocation() - FVector(0.0f, 0.0f, HalfHeight));
	const int32 ModelIndex = DisplayMode == 2 ? 1 : 0;
	const UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
	TArray<FTransform> PlannedRoots;
	PlannedRoots.Reserve(NumFrames);
	FVector PlannedPosition = GroundRoot.GetLocation();
	FVector PlannedVelocity = Movement->Velocity;
	PlannedVelocity.Z = 0.0f;
	FVector Input = Character->GetLastMovementInputVector();
	Input.Z = 0.0f;
	const float InputStrength = FMath::Clamp(Input.Size2D(), 0.0f, 1.0f);
	const FVector DesiredVelocity = Input.GetSafeNormal2D() * (Movement->GetMaxSpeed() * InputStrength);
	float PlannedYaw = GroundRoot.Rotator().Yaw;
	const float RotationRate = FMath::Abs(Movement->RotationRate.Yaw);
	for (int32 Frame = 0; Frame < NumFrames; ++Frame)
	{
		if (Frame > 0)
		{
			const float Acceleration = InputStrength > KINDA_SMALL_NUMBER
				? Movement->GetMaxAcceleration() : Movement->BrakingDecelerationWalking;
			PlannedVelocity = FMath::VInterpConstantTo(PlannedVelocity, DesiredVelocity, SampleSeconds, Acceleration);
			PlannedPosition += PlannedVelocity * SampleSeconds;
			float DesiredYaw = PlannedYaw;
			if (Movement->bOrientRotationToMovement && InputStrength > KINDA_SMALL_NUMBER)
			{
				DesiredYaw = DesiredVelocity.ToOrientationRotator().Yaw;
			}
			else if (Movement->bUseControllerDesiredRotation)
			{
				DesiredYaw = Character->GetControlRotation().Yaw;
			}
			const float DeltaYaw = FMath::FindDeltaAngleDegrees(PlannedYaw, DesiredYaw);
			PlannedYaw = FRotator::NormalizeAxis(PlannedYaw + FMath::Clamp(DeltaYaw,
				-RotationRate * SampleSeconds, RotationRate * SampleSeconds));
		}
		PlannedRoots.Emplace(FRotator(0.0f, PlannedYaw, 0.0f), PlannedPosition);
	}
	if (Runtime->GeneratedFrame >= 4 && !Runtime->Predict(ModelIndex, GroundRoot, Movement->Velocity, &PlannedRoots))
	{
		UE_LOG(LogTemp, Error, TEXT("AIAnimationLivePose: %s"), *Runtime->Error);
		bHasPose = false;
		return;
	}
	bHasPose = Runtime->BuildLocalPose(Runtime->Generated.GetData() + Runtime->GeneratedFrame * PoseValues, LatestLocalPose);
	if (!bHasPose)
	{
		Runtime->Error = TEXT("模型姿态包含无效变换");
		return;
	}
	Runtime->AppendHistory(GroundRoot);
}

bool UAIAnimationLivePoseComponent::CopyLatestPose(TArray<FName>& OutBoneNames, TArray<FTransform>& OutLocalPose) const
{
	if (!IsModelReady() || !bHasPose || DisplayMode == 0 || BoneNames.Num() != LatestLocalPose.Num())
	{
		return false;
	}
	OutBoneNames = BoneNames;
	OutLocalPose = LatestLocalPose;
	return true;
}

bool UAIAnimationLivePoseComponent::IsModelReady() const
{
	return Runtime && StartupError.IsEmpty() && Runtime->Error.IsEmpty();
}

float UAIAnimationLivePoseComponent::GetLastInferenceMs() const
{
	return Runtime ? Runtime->LastInferenceMs : 0.0f;
}

int32 UAIAnimationLivePoseComponent::GetInferenceCount() const
{
	return Runtime ? Runtime->NumInference : 0;
}

const FString& UAIAnimationLivePoseComponent::GetLastError() const
{
	return StartupError.IsEmpty() && Runtime ? Runtime->Error : StartupError;
}

AAIAnimationPlayableCharacter::AAIAnimationPlayableCharacter()
{
	PrimaryActorTick.bCanEverTick = true;
	bUseControllerRotationYaw = true;
	GetCapsuleComponent()->InitCapsuleSize(42.0f, 96.0f);
	GetMesh()->SetVisibility(false);
	PoseMesh = CreateDefaultSubobject<UPoseableMeshComponent>(TEXT("ModelPose"));
	PoseMesh->SetupAttachment(GetRootComponent());
	PoseMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	CameraArm = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraArm"));
	CameraArm->SetupAttachment(GetRootComponent());
	CameraArm->TargetArmLength = 430.0f;
	CameraArm->SetRelativeLocation(FVector(0.0f, 0.0f, -20.0f));
	CameraArm->SetRelativeRotation(FRotator(-16.0f, 0.0f, 0.0f));
	CameraArm->bDoCollisionTest = false;
	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("PlayerCamera"));
	Camera->SetupAttachment(CameraArm);
	UCharacterMovementComponent* Movement = GetCharacterMovement();
	Movement->bOrientRotationToMovement = false;
	Movement->MaxWalkSpeed = 165.0f;
	Movement->MaxWalkSpeedCrouched = 120.0f;
	Movement->MaxAcceleration = 800.0f;
	Movement->BrakingDecelerationWalking = 800.0f;
	Movement->GetNavAgentPropertiesRef().bCanCrouch = true;
}

AAIAnimationPlayableCharacter::~AAIAnimationPlayableCharacter()
{
	delete Runtime;
}

void AAIAnimationPlayableCharacter::BeginPlay()
{
	Super::BeginPlay();
	SetActorLocation(FVector(0.0f, 0.0f, 96.0f));
	PrimaryActorTick.AddPrerequisite(GetCharacterMovement(), GetCharacterMovement()->PrimaryComponentTick);
	USkeletalMesh* SkeletalAsset = LoadObject<USkeletalMesh>(nullptr, TEXT("/Game/Characters/UEFN_Mannequin/Meshes/SKM_UEFN_Mannequin.SKM_UEFN_Mannequin"));
	if (!SkeletalAsset)
	{
		UE_LOG(LogTemp, Error, TEXT("AIAnimationPlayable: UEFN Mannequin 未加载"));
		return;
	}
	PoseMesh->SetSkinnedAssetAndUpdate(SkeletalAsset);
	UMaterialInterface* Material = LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	for (int32 Index = 0; Index < PoseMesh->GetNumMaterials(); ++Index)
	{
		PoseMesh->SetMaterial(Index, Material);
	}
	const FString Bundle = FPlatformMisc::GetEnvironmentVariable(TEXT("AIANIMATION_PLAYABLE_BUNDLE"));
	Runtime = new FAIAnimationPlayableRuntime();
	if (Bundle.IsEmpty() || !Runtime->Initialize(Bundle, *SkeletalAsset))
	{
		Runtime->Error = Bundle.IsEmpty() ? TEXT("未设置 AIANIMATION_PLAYABLE_BUNDLE") : Runtime->Error;
		UE_LOG(LogTemp, Error, TEXT("AIAnimationPlayable: %s"), *Runtime->Error);
		return;
	}
	PoseMesh->SetRelativeLocation(FVector(0.0f, 0.0f, -GetCapsuleComponent()->GetScaledCapsuleHalfHeight()));
	const FTransform GroundRoot(GetActorQuat(), GetActorLocation() - FVector(0.0f, 0.0f, GetCapsuleComponent()->GetScaledCapsuleHalfHeight()));
	Runtime->Reset(GroundRoot);
	Runtime->ApplyPose(*PoseMesh, Runtime->SeedPose.GetData() + (NumFrames - 1) * PoseValues);
	UE_LOG(LogTemp, Display, TEXT("AIAnimationPlayable: live CMC model test ready; bundle=%s"), *Bundle);
}

void AAIAnimationPlayableCharacter::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (Runtime && !Runtime->Trace.IsEmpty())
	{
		const FString Output = FPaths::ProjectSavedDir() / TEXT("AIAnimation/PlayableTrace.csv");
		IFileManager::Get().MakeDirectory(*FPaths::GetPath(Output), true);
		FFileHelper::SaveStringToFile(Runtime->Trace, *Output);
		UE_LOG(LogTemp, Display, TEXT("AIAnimationPlayable: trace=%s"), *Output);
	}
	delete Runtime;
	Runtime = nullptr;
	Super::EndPlay(EndPlayReason);
}

void AAIAnimationPlayableCharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const FVector Desired = GetActorForwardVector() * float(int32(bForward) - int32(bBackward))
		+ GetActorRightVector() * float(int32(bRight) - int32(bLeft));
	if (!Desired.IsNearlyZero())
	{
		AddMovementInput(Desired.GetSafeNormal());
	}
	if (bTurnLeft != bTurnRight)
	{
		AddControllerYawInput((bTurnRight ? 1.0f : -1.0f) * DeltaSeconds * 90.0f);
	}
	PoseMesh->SetRelativeLocation(FVector(0.0f, 0.0f, -GetCapsuleComponent()->GetScaledCapsuleHalfHeight()));
	if (Runtime && Runtime->Error.IsEmpty())
	{
		SamplingRemainderSeconds += FMath::Clamp(DeltaSeconds, 0.0f, 0.1f);
		for (int32 Steps = 0; SamplingRemainderSeconds >= SampleSeconds && Steps < 4; ++Steps)
		{
			SamplingRemainderSeconds -= SampleSeconds;
			StepModel();
		}
	}
	ShowDiagnostics();
}

void AAIAnimationPlayableCharacter::StepModel()
{
	const double HalfHeight = GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	const FTransform GroundRoot(GetActorQuat(), GetActorLocation() - FVector(0.0, 0.0, HalfHeight));
	if (Runtime->GeneratedFrame >= 4 && !Runtime->Predict(ActiveModelIndex, GroundRoot, GetCharacterMovement()->Velocity))
	{
		UE_LOG(LogTemp, Error, TEXT("AIAnimationPlayable: %s"), *Runtime->Error);
		return;
	}
	if (!Runtime->ApplyPose(*PoseMesh, Runtime->Generated.GetData() + Runtime->GeneratedFrame * PoseValues))
	{
		Runtime->Error = TEXT("模型姿态包含无效变换");
		return;
	}
	const FVector Left = PoseMesh->GetBoneLocationByName(TEXT("foot_l"), EBoneSpaces::WorldSpace);
	const FVector Right = PoseMesh->GetBoneLocationByName(TEXT("foot_r"), EBoneSpaces::WorldSpace);
	const FVector Position = GetActorLocation();
	const FVector Velocity = GetCharacterMovement()->Velocity;
	Runtime->Trace += FString::Printf(TEXT("%d,%d,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%d,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f\n"),
		Runtime->NumSamples++, ActiveModelIndex, Position.X, Position.Y, Position.Z, Velocity.X, Velocity.Y, Velocity.Z, bIsCrouched ? 1 : 0,
		Left.X, Left.Y, Left.Z, Right.X, Right.Y, Right.Z, Runtime->LastInferenceMs);
	Runtime->AppendHistory(GroundRoot);
}

void AAIAnimationPlayableCharacter::ShowDiagnostics() const
{
	if (!GEngine)
	{
		return;
	}
	const FString ModelName = ActiveModelIndex == 0 ? TEXT("CONTROL") : TEXT("SPEED/PHASE PILOT");
	const FString Status = !Runtime ? TEXT("网格加载失败") : Runtime->Error.IsEmpty() ? TEXT("LIVE NNE") : Runtime->Error;
	GEngine->AddOnScreenDebugMessage(9100, 0.0f, Runtime && Runtime->Error.IsEmpty() ? FColor::Green : FColor::Red,
		FString::Printf(TEXT("AIAnimation 玩家实测 | %s | %s | %.0f cm/s | NNE %.2f ms | #%d"), *Status, *ModelName,
			GetVelocity().Size2D(), Runtime ? Runtime->LastInferenceMs : 0.0f, Runtime ? Runtime->NumInference : 0));
	GEngine->AddOnScreenDebugMessage(9101, 0.0f, FColor::White,
		TEXT("WASD 移动  鼠标/QE 转向  Shift 跑  C 蹲  1/2 切换模型  R 重置  Esc 退出"));
	GEngine->AddOnScreenDebugMessage(9102, 0.0f, bIsCrouched ? FColor::Yellow : FColor::White,
		bIsCrouched ? TEXT("Crouch: CMC 已蹲下；当前模型无 Stand/Crouch 输入，姿态切换属于待解决问题") : TEXT("Stand: Root/位移由 CMC 控制，姿态由无参考模型生成"));
}

void AAIAnimationPlayableCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);
	PlayerInputComponent->BindKey(EKeys::W, IE_Pressed, this, &AAIAnimationPlayableCharacter::PressForward);
	PlayerInputComponent->BindKey(EKeys::W, IE_Released, this, &AAIAnimationPlayableCharacter::ReleaseForward);
	PlayerInputComponent->BindKey(EKeys::S, IE_Pressed, this, &AAIAnimationPlayableCharacter::PressBackward);
	PlayerInputComponent->BindKey(EKeys::S, IE_Released, this, &AAIAnimationPlayableCharacter::ReleaseBackward);
	PlayerInputComponent->BindKey(EKeys::D, IE_Pressed, this, &AAIAnimationPlayableCharacter::PressRight);
	PlayerInputComponent->BindKey(EKeys::D, IE_Released, this, &AAIAnimationPlayableCharacter::ReleaseRight);
	PlayerInputComponent->BindKey(EKeys::A, IE_Pressed, this, &AAIAnimationPlayableCharacter::PressLeft);
	PlayerInputComponent->BindKey(EKeys::A, IE_Released, this, &AAIAnimationPlayableCharacter::ReleaseLeft);
	PlayerInputComponent->BindAxisKey(EKeys::MouseX, this, &AAIAnimationPlayableCharacter::TurnMouse);
	PlayerInputComponent->BindKey(EKeys::Q, IE_Pressed, this, &AAIAnimationPlayableCharacter::PressTurnLeft);
	PlayerInputComponent->BindKey(EKeys::Q, IE_Released, this, &AAIAnimationPlayableCharacter::ReleaseTurnLeft);
	PlayerInputComponent->BindKey(EKeys::E, IE_Pressed, this, &AAIAnimationPlayableCharacter::PressTurnRight);
	PlayerInputComponent->BindKey(EKeys::E, IE_Released, this, &AAIAnimationPlayableCharacter::ReleaseTurnRight);
	PlayerInputComponent->BindKey(EKeys::LeftShift, IE_Pressed, this, &AAIAnimationPlayableCharacter::StartRun);
	PlayerInputComponent->BindKey(EKeys::LeftShift, IE_Released, this, &AAIAnimationPlayableCharacter::StopRun);
	PlayerInputComponent->BindKey(EKeys::C, IE_Pressed, this, &AAIAnimationPlayableCharacter::ToggleCrouch);
	PlayerInputComponent->BindKey(EKeys::One, IE_Pressed, this, &AAIAnimationPlayableCharacter::UseControlModel);
	PlayerInputComponent->BindKey(EKeys::Two, IE_Pressed, this, &AAIAnimationPlayableCharacter::UsePilotModel);
	PlayerInputComponent->BindKey(EKeys::R, IE_Pressed, this, &AAIAnimationPlayableCharacter::ResetPlayback);
	PlayerInputComponent->BindKey(EKeys::Escape, IE_Pressed, this, &AAIAnimationPlayableCharacter::QuitTest);
}

void AAIAnimationPlayableCharacter::PressForward() { bForward = true; }
void AAIAnimationPlayableCharacter::ReleaseForward() { bForward = false; }
void AAIAnimationPlayableCharacter::PressBackward() { bBackward = true; }
void AAIAnimationPlayableCharacter::ReleaseBackward() { bBackward = false; }
void AAIAnimationPlayableCharacter::PressRight() { bRight = true; }
void AAIAnimationPlayableCharacter::ReleaseRight() { bRight = false; }
void AAIAnimationPlayableCharacter::PressLeft() { bLeft = true; }
void AAIAnimationPlayableCharacter::ReleaseLeft() { bLeft = false; }
void AAIAnimationPlayableCharacter::TurnMouse(float Value) { AddControllerYawInput(Value); }
void AAIAnimationPlayableCharacter::PressTurnLeft() { bTurnLeft = true; }
void AAIAnimationPlayableCharacter::ReleaseTurnLeft() { bTurnLeft = false; }
void AAIAnimationPlayableCharacter::PressTurnRight() { bTurnRight = true; }
void AAIAnimationPlayableCharacter::ReleaseTurnRight() { bTurnRight = false; }

void AAIAnimationPlayableCharacter::StartRun()
{
	GetCharacterMovement()->MaxWalkSpeed = 375.0f;
}

void AAIAnimationPlayableCharacter::StopRun()
{
	GetCharacterMovement()->MaxWalkSpeed = 165.0f;
}

void AAIAnimationPlayableCharacter::ToggleCrouch()
{
	if (bIsCrouched)
	{
		UnCrouch();
	}
	else
	{
		Crouch();
	}
}

void AAIAnimationPlayableCharacter::UseControlModel()
{
	ActiveModelIndex = 0;
	if (Runtime && Runtime->Error.IsEmpty())
	{
		const FTransform GroundRoot(GetActorQuat(), GetActorLocation() - FVector(0.0, 0.0, GetCapsuleComponent()->GetScaledCapsuleHalfHeight()));
		Runtime->Reset(GroundRoot);
	}
}

void AAIAnimationPlayableCharacter::UsePilotModel()
{
	ActiveModelIndex = 1;
	if (Runtime && Runtime->Error.IsEmpty())
	{
		const FTransform GroundRoot(GetActorQuat(), GetActorLocation() - FVector(0.0, 0.0, GetCapsuleComponent()->GetScaledCapsuleHalfHeight()));
		Runtime->Reset(GroundRoot);
	}
}

void AAIAnimationPlayableCharacter::ResetPlayback()
{
	GetCharacterMovement()->StopMovementImmediately();
	SetActorLocationAndRotation(FVector(0.0f, 0.0f, 96.0f), FRotator::ZeroRotator);
	if (Runtime && Runtime->Error.IsEmpty())
	{
		const FTransform GroundRoot(GetActorQuat(), GetActorLocation() - FVector(0.0, 0.0, GetCapsuleComponent()->GetScaledCapsuleHalfHeight()));
		Runtime->Reset(GroundRoot);
		Runtime->ApplyPose(*PoseMesh, Runtime->SeedPose.GetData() + (NumFrames - 1) * PoseValues);
	}
}

void AAIAnimationPlayableCharacter::QuitTest()
{
	if (APlayerController* Player = Cast<APlayerController>(GetController()))
	{
		Player->ConsoleCommand(TEXT("quit"), true);
	}
}

AAIAnimationPlayableGameMode::AAIAnimationPlayableGameMode()
{
	PrimaryActorTick.bCanEverTick = true;
	DefaultPawnClass = AAIAnimationPlayableCharacter::StaticClass();
}

void AAIAnimationPlayableGameMode::StartPlay()
{
	UWorld* World = GetWorld();
	AStaticMeshActor* Floor = World->SpawnActor<AStaticMeshActor>(FVector(0.0f, 0.0f, -50.0f), FRotator::ZeroRotator);
	if (Floor)
	{
		UStaticMeshComponent* Surface = Floor->GetStaticMeshComponent();
		Surface->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")));
		Surface->SetMobility(EComponentMobility::Movable);
		Surface->SetCollisionProfileName(TEXT("BlockAll"));
		Floor->SetActorScale3D(FVector(100.0f, 100.0f, 1.0f));
	}
	ADirectionalLight* Sun = World->SpawnActor<ADirectionalLight>(FVector(0.0f, 0.0f, 400.0f), FRotator(-50.0f, -30.0f, 0.0f));
	if (Sun)
	{
		Sun->GetLightComponent()->SetMobility(EComponentMobility::Movable);
	}
	APointLight* Fill = World->SpawnActor<APointLight>(FVector(100.0f, 100.0f, 300.0f), FRotator::ZeroRotator);
	if (Fill)
	{
		Fill->PointLightComponent->SetMobility(EComponentMobility::Movable);
		Fill->PointLightComponent->SetIntensity(18000.0f);
	}
	Super::StartPlay();
}

void AAIAnimationPlayableGameMode::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	for (int32 Index = -15; Index <= 15; ++Index)
	{
		const double Coordinate = Index * 200.0;
		const FColor Color = Index == 0 ? FColor::Cyan : FColor(70, 90, 110);
		DrawDebugLine(GetWorld(), FVector(Coordinate, -3000.0, 1.0), FVector(Coordinate, 3000.0, 1.0), Color, false, 0.0f, 0, 1.0f);
		DrawDebugLine(GetWorld(), FVector(-3000.0, Coordinate, 1.0), FVector(3000.0, Coordinate, 1.0), Color, false, 0.0f, 0, 1.0f);
	}
}
