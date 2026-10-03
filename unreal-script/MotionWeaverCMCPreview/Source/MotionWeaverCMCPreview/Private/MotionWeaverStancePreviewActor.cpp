// Copyright ZhaoZining. All Rights Reserved.

/**
 * @file MotionWeaverStancePreviewActor.cpp
 * @brief 在单机预览中以 CMC 执行 Root 为唯一位移，绑定 B1 的本地 DirectML 姿态输出。
 */

#include "MotionWeaverStancePreviewActor.h"

#include "Components/PoseableMeshComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/Engine.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Math/RotationMatrix.h"
#include "Misc/CommandLine.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "NNEModelData.h"
#include "Serialization/JsonSerializer.h"
#include "HAL/FileManager.h"

DEFINE_LOG_CATEGORY_STATIC(LogMotionWeaverStancePreview, Log, All);

namespace
{
	constexpr int32 NumHistoryFrames = 24;
	constexpr int32 NumFutureFrames = 24;
	constexpr int32 NumBones = 79;
	constexpr int32 PoseValuesPerBone = 9;
	constexpr int32 HistoryValuesPerFrame = NumBones * PoseValuesPerBone + 7;
	constexpr float SampleIntervalSeconds = 1.0f / 30.0f;

	FVector ToMotionAxes(const FVector& UnrealVector)
	{
		return FVector(-UnrealVector.Y, UnrealVector.Z, UnrealVector.X);
	}

	FVector ToUnrealAxes(const FVector& MotionVector)
	{
		return FVector(MotionVector.Z, -MotionVector.X, MotionVector.Y);
	}

	FQuat ToMotionRotation(const FQuat& UnrealRotation)
	{
		const FVector MotionX = ToMotionAxes(UnrealRotation.RotateVector(FVector(0.0, -1.0, 0.0)));
		const FVector MotionY = ToMotionAxes(UnrealRotation.RotateVector(FVector::UpVector));
		return FRotationMatrix::MakeFromXY(MotionX, MotionY).ToQuat();
	}

	FQuat ToUnrealRotation(const FVector& MotionX, const FVector& MotionY)
	{
		const FVector X = MotionX.GetSafeNormal();
		const FVector Y = (MotionY - FVector::DotProduct(MotionY, X) * X).GetSafeNormal();
		if (X.IsNearlyZero() || Y.IsNearlyZero())
		{
			return FQuat::Identity;
		}
		const FVector Z = FVector::CrossProduct(X, Y).GetSafeNormal();
		return FRotationMatrix::MakeFromXY(ToUnrealAxes(Z), ToUnrealAxes(-X)).ToQuat();
	}

	bool ReadNumbers(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key, int32 Count, TArray<double>& OutValues)
	{
		const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
		if (!Object.IsValid() || !Object->TryGetArrayField(Key, Values) || Values->Num() != Count)
		{
			return false;
		}
		OutValues.Reset(Count);
		for (const TSharedPtr<FJsonValue>& Value : *Values)
		{
			double Number = 0.0;
			if (!Value.IsValid() || !Value->TryGetNumber(Number) || !FMath::IsFinite(Number))
			{
				return false;
			}
			OutValues.Add(Number);
		}
		return true;
	}

	bool ReadVectors(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key, TArray<FVector>& OutVectors)
	{
		const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
		if (!Object.IsValid() || !Object->TryGetArrayField(Key, Values) || Values->Num() != NumBones)
		{
			return false;
		}
		OutVectors.Reset(NumBones);
		for (const TSharedPtr<FJsonValue>& Value : *Values)
		{
			if (!Value.IsValid() || Value->Type != EJson::Array)
			{
				return false;
			}
			const TArray<TSharedPtr<FJsonValue>>& Coordinates = Value->AsArray();
			if (Coordinates.Num() != 3)
			{
				return false;
			}
			TArray<double> Numbers;
			Numbers.Reserve(3);
			for (const TSharedPtr<FJsonValue>& Coordinate : Coordinates)
			{
				double Number = 0.0;
				if (!Coordinate.IsValid() || !Coordinate->TryGetNumber(Number) || !FMath::IsFinite(Number))
				{
					return false;
				}
				Numbers.Add(Number);
			}
			OutVectors.Add(FVector(Numbers[0], Numbers[1], Numbers[2]));
		}
		return true;
	}
}

AMotionWeaverStancePreviewActor::AMotionWeaverStancePreviewActor()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;
	SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SceneRoot"));
	SetRootComponent(SceneRoot);
	ModelMesh = CreateDefaultSubobject<UPoseableMeshComponent>(TEXT("ModelMesh"));
	ModelMesh->SetupAttachment(SceneRoot);
	ModelMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	ModelMesh->SetVisibility(false);
}

void AMotionWeaverStancePreviewActor::BeginPlay()
{
	Super::BeginPlay();
	FString Folder;
	if (!FParse::Value(FCommandLine::Get(), TEXT("MotionWeaverModelFolder="), Folder))
	{
		SetActorTickEnabled(false);
		return;
	}
	bUseFeedback = FParse::Param(FCommandLine::Get(), TEXT("MotionWeaverFeedback"));
	bEnabled = LoadModel(Folder);
	if (!bEnabled)
	{
		UE_LOG(LogMotionWeaverStancePreview, Error, TEXT("MW_MODEL_INIT_FAIL: %s"), *Folder);
		SetActorTickEnabled(false);
	}
}

bool AMotionWeaverStancePreviewActor::LoadModel(const FString& Folder)
{
	FString Json;
	TArray<uint8> ModelBytes;
	TSharedPtr<FJsonObject> Manifest;
	if (!FFileHelper::LoadFileToString(Json, *(Folder / TEXT("manifest.json"))) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Manifest)
		|| !FFileHelper::LoadFileToArray(ModelBytes, *(Folder / TEXT("model.onnx"))))
	{
		UE_LOG(LogMotionWeaverStancePreview, Error, TEXT("MW_MODEL_INIT_STAGE_FAIL: load manifest or model"));
		return false;
	}
	FString Format;
	int32 BoneCount = 0;
	int32 HistoryCount = 0;
	int32 FutureCount = 0;
	if (!Manifest.IsValid() || !Manifest->TryGetStringField(TEXT("format"), Format) || Format != TEXT("motionweaver_stance_pilot_onnx_v1")
		|| !Manifest->TryGetNumberField(TEXT("bone_count"), BoneCount) || BoneCount != NumBones
		|| !Manifest->TryGetNumberField(TEXT("history_frames"), HistoryCount) || HistoryCount != ::NumHistoryFrames
		|| !Manifest->TryGetNumberField(TEXT("future_frames"), FutureCount) || FutureCount != NumFutureFrames
		|| !ReadVectors(Manifest, TEXT("pose_mean_m"), PoseMeanMeters) || !ReadVectors(Manifest, TEXT("pose_std_m"), PoseStdMeters))
	{
		UE_LOG(LogMotionWeaverStancePreview, Error, TEXT("MW_MODEL_INIT_STAGE_FAIL: contract format=%s bones=%d history=%d future=%d mean=%d std=%d"),
			*Format, BoneCount, HistoryCount, FutureCount, PoseMeanMeters.Num(), PoseStdMeters.Num());
		return false;
	}
	for (const FVector& StandardDeviation : PoseStdMeters)
	{
		if (StandardDeviation.X <= 0.0 || StandardDeviation.Y <= 0.0 || StandardDeviation.Z <= 0.0)
		{
			UE_LOG(LogMotionWeaverStancePreview, Error, TEXT("MW_MODEL_INIT_STAGE_FAIL: non-positive pose standard deviation"));
			return false;
		}
	}
	const TArray<TSharedPtr<FJsonValue>>* BoneValues = nullptr;
	if (!Manifest->TryGetArrayField(TEXT("bones"), BoneValues) || BoneValues->Num() != NumBones)
	{
		UE_LOG(LogMotionWeaverStancePreview, Error, TEXT("MW_MODEL_INIT_STAGE_FAIL: bone list"));
		return false;
	}
	Bones.Reserve(NumBones);
	for (int32 Index = 0; Index < NumBones; ++Index)
	{
		const TSharedPtr<FJsonObject> BoneObject = (*BoneValues)[Index].IsValid() ? (*BoneValues)[Index]->AsObject() : nullptr;
		TArray<double> Position;
		TArray<double> Rotation;
		FString Name;
		int32 ParentIndex = INDEX_NONE;
		if (!BoneObject.IsValid() || !BoneObject->TryGetStringField(TEXT("name"), Name) || Name.IsEmpty()
			|| !BoneObject->TryGetNumberField(TEXT("parent"), ParentIndex) || !ReadNumbers(BoneObject, TEXT("position"), 3, Position)
			|| !ReadNumbers(BoneObject, TEXT("rotation"), 4, Rotation)
			|| (Index == 0 ? ParentIndex != INDEX_NONE : ParentIndex < 0 || ParentIndex >= Index))
		{
			UE_LOG(LogMotionWeaverStancePreview, Error, TEXT("MW_MODEL_INIT_STAGE_FAIL: bone %d"), Index);
			return false;
		}
		FBoneContract Bone;
		Bone.Name = FName(*Name);
		Bone.ParentIndex = ParentIndex;
		Bone.ReferencePositionCm = FVector(Position[0], Position[1], Position[2]);
		Bone.ReferenceRotation = FQuat(Rotation[0], Rotation[1], Rotation[2], Rotation[3]).GetNormalized();
		if (Bone.Name.IsNone() || Bone.ReferenceRotation.ContainsNaN())
		{
			UE_LOG(LogMotionWeaverStancePreview, Error, TEXT("MW_MODEL_INIT_STAGE_FAIL: bone transform %d"), Index);
			return false;
		}
		Bones.Add(Bone);
	}
	ModelData = NewObject<UNNEModelData>(this);
	ModelData->Init(TEXT("onnx"), MakeArrayView(ModelBytes));
	ModelData->SetTargetRuntimes({ TEXT("NNERuntimeORTDml") });
	TWeakInterfacePtr<INNERuntimeGPU> Runtime = UE::NNE::GetRuntime<INNERuntimeGPU>(TEXT("NNERuntimeORTDml"));
	if (!Runtime.IsValid() || Runtime->CanCreateModelGPU(ModelData) != UE::NNE::EResultStatus::Ok)
	{
		UE_LOG(LogMotionWeaverStancePreview, Error, TEXT("MW_MODEL_INIT_STAGE_FAIL: DirectML runtime or ONNX model"));
		return false;
	}
	TSharedPtr<UE::NNE::IModelGPU> Model = Runtime->CreateModelGPU(ModelData);
	Instance = Model ? Model->CreateModelInstanceGPU() : nullptr;
	if (!Instance || Instance->GetInputTensorDescs().Num() != 3 || Instance->GetOutputTensorDescs().Num() != 1)
	{
		UE_LOG(LogMotionWeaverStancePreview, Error, TEXT("MW_MODEL_INIT_STAGE_FAIL: tensor count"));
		return false;
	}
	const TArray<UE::NNE::FTensorShape> Shapes = { UE::NNE::FTensorShape::Make({ 1u, 24u, 718u }),
		UE::NNE::FTensorShape::Make({ 1u, 24u, 7u }), UE::NNE::FTensorShape::Make({ 1u, 24u, 1u }) };
	if (Instance->SetInputTensorShapes(Shapes) != UE::NNE::EResultStatus::Ok || Instance->GetOutputTensorShapes().Num() != 1
		|| Instance->GetOutputTensorShapes()[0].Volume() != uint64(NumFutureFrames * NumBones * PoseValuesPerBone))
	{
		UE_LOG(LogMotionWeaverStancePreview, Error, TEXT("MW_MODEL_INIT_STAGE_FAIL: fixed tensor shapes"));
		return false;
	}
	for (const UE::NNE::FTensorDesc& Description : Instance->GetInputTensorDescs())
	{
		if (Description.GetDataType() != ENNETensorDataType::Float)
		{
			return false;
		}
	}
	if (Instance->GetOutputTensorDescs()[0].GetDataType() != ENNETensorDataType::Float)
	{
		return false;
	}
	History.SetNumZeroed(::NumHistoryFrames * HistoryValuesPerFrame);
	HistoryRoots.Reserve(::NumHistoryFrames);
	FutureRoot.SetNumZeroed(NumFutureFrames * 7);
	GoalStance.SetNumZeroed(NumFutureFrames);
	Prediction.SetNumZeroed(NumFutureFrames * NumBones * PoseValuesPerBone);
	TelemetryRows.Add(TEXT("time_seconds,inferences,failures,cmc_wants_crouch,accepted_crouch,root_x_cm,root_y_cm,root_z_cm,speed_cm_s,model_source_joint_rmse_cm,pelvis_z_cm,model_foot_l_z_cm,model_foot_r_z_cm,inference_ms"));
	UE_LOG(LogMotionWeaverStancePreview, Display, TEXT("MW_MODEL_READY: B1 DirectML bones=%d history=%d future=%d"), NumBones, ::NumHistoryFrames, NumFutureFrames);
	return true;
}

void AMotionWeaverStancePreviewActor::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	ElapsedSeconds += DeltaSeconds;
	if (!bEnabled)
	{
		return;
	}
	if (!TrackedCharacter.IsValid())
	{
		TrackedCharacter = UGameplayStatics::GetPlayerCharacter(this, 0);
	}
	ACharacter* Character = TrackedCharacter.Get();
	if (!Character || !Character->GetMesh())
	{
		return;
	}
	if (!ModelMesh->GetSkinnedAsset())
	{
		for (const FBoneContract& Bone : Bones)
		{
			if (Character->GetMesh()->GetBoneIndex(Bone.Name) == INDEX_NONE)
			{
				UE_LOG(LogMotionWeaverStancePreview, Error, TEXT("MW_MODEL_INIT_STAGE_FAIL: missing mesh bone %s"), *Bone.Name.ToString());
				bEnabled = false;
				SetActorTickEnabled(false);
				return;
			}
		}
		ModelMesh->SetSkinnedAssetAndUpdate(Character->GetMesh()->GetSkinnedAsset());
		for (int32 MaterialIndex = 0; MaterialIndex < Character->GetMesh()->GetNumMaterials(); ++MaterialIndex)
		{
			ModelMesh->SetMaterial(MaterialIndex, Character->GetMesh()->GetMaterial(MaterialIndex));
		}
		AddTickPrerequisiteActor(Character);
		PrimaryActorTick.AddPrerequisite(Character->GetMesh(), Character->GetMesh()->PrimaryComponentTick);
	}
	SampleRemainderSeconds += DeltaSeconds;
	if (SampleRemainderSeconds >= SampleIntervalSeconds)
	{
		SampleRemainderSeconds -= SampleIntervalSeconds;
		if (!CaptureHistory(*Character))
		{
			RestoreSourceMesh();
			return;
		}
		++SamplesSinceInference;
		if (NumHistoryFrames > 0 && (NumInferences == 0 || SamplesSinceInference >= 4))
		{
			if (!InferFuture(*Character))
			{
				++NumInferenceFailures;
				RestoreSourceMesh();
				return;
			}
			++NumInferences;
			SamplesSinceInference = 0;
		}
	}
	if (NumInferences > 0 && !ApplyPredictedPose(*Character))
	{
		++NumInferenceFailures;
		RestoreSourceMesh();
		return;
	}
	if (GEngine)
	{
		const FString Status = FString::Printf(TEXT("MotionWeaver B1 MODEL POSE | DirectML inference=%d fail=%d %.2f ms | CMC accepted=%s | history=%s | online Root=constant velocity (not oracle)"),
			NumInferences, NumInferenceFailures, LastInferenceMilliseconds, Character->IsCrouched() ? TEXT("CROUCH") : TEXT("STAND"),
			bUseFeedback ? TEXT("generated feedback") : TEXT("GASP source"));
		GEngine->AddOnScreenDebugMessage(270929, 0.25f, FColor::Green, Status);
	}
}

bool AMotionWeaverStancePreviewActor::CaptureHistory(const ACharacter& Character)
{
	const USkinnedMeshComponent* HistoryMesh = bUseFeedback && bPoseVisible ? static_cast<const USkinnedMeshComponent*>(ModelMesh.Get()) : static_cast<const USkinnedMeshComponent*>(Character.GetMesh());
	const FTransform SourceRoot = HistoryMesh->GetSocketTransform(TEXT("root"), RTS_Component);
	if (SourceRoot.ContainsNaN())
	{
		return false;
	}
	if (NumHistoryFrames == ::NumHistoryFrames)
	{
		FMemory::Memmove(History.GetData(), History.GetData() + HistoryValuesPerFrame, (::NumHistoryFrames - 1) * HistoryValuesPerFrame * sizeof(float));
		HistoryRoots.RemoveAt(0);
	}
	else
	{
		++NumHistoryFrames;
	}
	float* Frame = History.GetData() + (NumHistoryFrames - 1) * HistoryValuesPerFrame;
	for (int32 Index = 0; Index < ::NumBones; ++Index)
	{
		const FTransform SourceBone = HistoryMesh->GetSocketTransform(Bones[Index].Name, RTS_Component).GetRelativeTransform(SourceRoot);
		const FVector Position = ToMotionAxes(SourceBone.GetTranslation()) * 0.01;
		const FVector Normalized = (Position - PoseMeanMeters[Index]) / PoseStdMeters[Index];
		const FQuat Rotation = ToMotionRotation(SourceBone.GetRotation() * Bones[Index].ReferenceRotation.Inverse());
		const FVector AxisX = Rotation.RotateVector(FVector::ForwardVector);
		const FVector AxisY = Rotation.RotateVector(FVector::RightVector);
		float* Values = Frame + Index * PoseValuesPerBone;
		Values[0] = float(Normalized.X); Values[1] = float(Normalized.Y); Values[2] = float(Normalized.Z);
		Values[3] = float(AxisX.X); Values[4] = float(AxisY.X); Values[5] = float(AxisX.Y);
		Values[6] = float(AxisY.Y); Values[7] = float(AxisX.Z); Values[8] = float(AxisY.Z);
		for (int32 ValueIndex = 0; ValueIndex < PoseValuesPerBone; ++ValueIndex)
		{
			if (!FMath::IsFinite(Values[ValueIndex]))
			{
				return false;
			}
		}
	}
	HistoryRoots.Add(Character.GetActorTransform());
	return true;
}

bool AMotionWeaverStancePreviewActor::InferFuture(const ACharacter& Character)
{
	TArray<float> InputHistory;
	InputHistory.SetNumZeroed(::NumHistoryFrames * HistoryValuesPerFrame);
	const FTransform Origin = HistoryRoots.Last();
	const int32 Padding = ::NumHistoryFrames - NumHistoryFrames;
	for (int32 FrameIndex = 0; FrameIndex < ::NumHistoryFrames; ++FrameIndex)
	{
		const int32 SourceIndex = FMath::Max(0, FrameIndex - Padding);
		float* Target = InputHistory.GetData() + FrameIndex * HistoryValuesPerFrame;
		FMemory::Memcpy(Target, History.GetData() + SourceIndex * HistoryValuesPerFrame, NumBones * PoseValuesPerBone * sizeof(float));
		const FTransform& Root = HistoryRoots[SourceIndex];
		const FVector RelativeMeters = ToMotionAxes(Origin.InverseTransformPosition(Root.GetLocation())) * 0.01;
		const FQuat RelativeRotation = ToMotionRotation(Origin.GetRotation().Inverse() * Root.GetRotation());
		Target[711] = float(RelativeMeters.X); Target[712] = float(RelativeMeters.Y); Target[713] = float(RelativeMeters.Z);
		Target[714] = float(RelativeRotation.X); Target[715] = float(RelativeRotation.Y); Target[716] = float(RelativeRotation.Z); Target[717] = float(RelativeRotation.W);
	}
	const FVector VelocityLocal = Origin.InverseTransformVectorNoScale(Character.GetVelocity());
	for (int32 FrameIndex = 0; FrameIndex < NumFutureFrames; ++FrameIndex)
	{
		const FVector PositionMeters = ToMotionAxes(VelocityLocal * ((FrameIndex + 1) * SampleIntervalSeconds)) * 0.01;
		float* Root = FutureRoot.GetData() + FrameIndex * 7;
		Root[0] = float(PositionMeters.X); Root[1] = float(PositionMeters.Y); Root[2] = float(PositionMeters.Z);
		Root[3] = 0.0f; Root[4] = 0.0f; Root[5] = 0.0f; Root[6] = 1.0f;
		GoalStance[FrameIndex] = Character.IsCrouched() ? 1.0f : 0.0f;
	}
	UE::NNE::FTensorBindingCPU Bindings[3] = { { InputHistory.GetData(), uint64(InputHistory.Num()) * sizeof(float) },
		{ FutureRoot.GetData(), uint64(FutureRoot.Num()) * sizeof(float) }, { GoalStance.GetData(), uint64(GoalStance.Num()) * sizeof(float) } };
	UE::NNE::FTensorBindingCPU OutputBinding { Prediction.GetData(), uint64(Prediction.Num()) * sizeof(float) };
	const double Start = FPlatformTime::Seconds();
	const UE::NNE::EResultStatus Status = Instance->RunSync(MakeArrayView(Bindings), MakeArrayView(&OutputBinding, 1));
	LastInferenceMilliseconds = float((FPlatformTime::Seconds() - Start) * 1000.0);
	if (Status != UE::NNE::EResultStatus::Ok)
	{
		return false;
	}
	for (const float Value : Prediction)
	{
		if (!FMath::IsFinite(Value))
		{
			return false;
		}
	}
	if (NumInferences == 0 || NumInferences % 25 == 0)
	{
		UE_LOG(LogMotionWeaverStancePreview, Display, TEXT("MW_MODEL_INFER: count=%d ms=%.3f crouch=%d root=%s"), NumInferences + 1,
			LastInferenceMilliseconds, Character.IsCrouched(), *Character.GetActorLocation().ToCompactString());
	}
	return true;
}

bool AMotionWeaverStancePreviewActor::ApplyPredictedPose(const ACharacter& Character)
{
	USkeletalMeshComponent* SourceMesh = Character.GetMesh();
	if (!SourceMesh || !ModelMesh->GetSkinnedAsset())
	{
		return false;
	}
	ModelMesh->SetWorldTransform(SourceMesh->GetComponentTransform());
	ModelMesh->CopyPoseFromSkeletalComponent(SourceMesh);
	const FTransform Root = SourceMesh->GetSocketTransform(TEXT("root"), RTS_Component);
	const int32 FrameIndex = FMath::Clamp(SamplesSinceInference, 0, NumFutureFrames - 1);
	const float* Frame = Prediction.GetData() + FrameIndex * NumBones * PoseValuesPerBone;
	TArray<FTransform> ComponentPoses;
	ComponentPoses.Reserve(NumBones);
	double SquaredSourceDifference = 0.0;
	double PelvisHeightCm = 0.0;
	double LeftFootHeightCm = 0.0;
	double RightFootHeightCm = 0.0;
	for (int32 BoneIndex = 0; BoneIndex < NumBones; ++BoneIndex)
	{
		const float* Values = Frame + BoneIndex * PoseValuesPerBone;
		const FVector AxisX(Values[3], Values[5], Values[7]);
		const FVector AxisY(Values[4], Values[6], Values[8]);
		if (AxisX.SizeSquared() < 0.01 || AxisY.SizeSquared() < 0.01)
		{
			return false;
		}
		const FBoneContract& Bone = Bones[BoneIndex];
		const FQuat Rotation = (ToUnrealRotation(AxisX, AxisY) * Bone.ReferenceRotation).GetNormalized();
		FVector Position;
		if (Bone.ParentIndex == INDEX_NONE)
		{
			const FVector PredictedMeters = FVector(Values[0], Values[1], Values[2]) * PoseStdMeters[BoneIndex] + PoseMeanMeters[BoneIndex];
			Position = ToUnrealAxes(PredictedMeters) * 100.0;
			if (Position.ContainsNaN() || Position.Size() > 200.0)
			{
				return false;
			}
		}
		else
		{
			const FBoneContract& Parent = Bones[Bone.ParentIndex];
			const FVector LocalOffset = Parent.ReferenceRotation.Inverse().RotateVector(Bone.ReferencePositionCm - Parent.ReferencePositionCm);
			Position = ComponentPoses[Bone.ParentIndex].GetTranslation() + ComponentPoses[Bone.ParentIndex].GetRotation().RotateVector(LocalOffset);
		}
		const FTransform ComponentPose = FTransform(Rotation, Position) * Root;
		if (ComponentPose.ContainsNaN())
		{
			return false;
		}
		ComponentPoses.Add(ComponentPose);
		ModelMesh->SetBoneTransformByName(Bone.Name, ComponentPose, EBoneSpaces::ComponentSpace);
		SquaredSourceDifference += FVector::DistSquared(ComponentPose.GetTranslation(), SourceMesh->GetSocketTransform(Bone.Name, RTS_Component).GetTranslation());
		if (Bone.Name == TEXT("pelvis")) { PelvisHeightCm = ComponentPose.GetTranslation().Z; }
		if (Bone.Name == TEXT("foot_l")) { LeftFootHeightCm = ComponentPose.GetTranslation().Z; }
		if (Bone.Name == TEXT("foot_r")) { RightFootHeightCm = ComponentPose.GetTranslation().Z; }
	}
	if (TelemetryRows.Num() <= 18001 && NumInferences != LastRecordedInference)
	{
		LastRecordedInference = NumInferences;
		const FVector ActorRoot = Character.GetActorLocation();
		TelemetryRows.Add(FString::Printf(TEXT("%.4f,%d,%d,%d,%d,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f"), ElapsedSeconds,
			NumInferences, NumInferenceFailures, Character.GetCharacterMovement()->bWantsToCrouch, Character.IsCrouched(), ActorRoot.X, ActorRoot.Y, ActorRoot.Z,
			Character.GetVelocity().Size2D(), FMath::Sqrt(SquaredSourceDifference / NumBones), PelvisHeightCm, LeftFootHeightCm, RightFootHeightCm, LastInferenceMilliseconds));
	}
	ModelMesh->SetVisibility(true);
	SourceMesh->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
	SourceMesh->SetVisibility(false, false);
	bPoseVisible = true;
	return true;
}

void AMotionWeaverStancePreviewActor::RestoreSourceMesh()
{
	if (ACharacter* Character = TrackedCharacter.Get())
	{
		if (USkeletalMeshComponent* SourceMesh = Character->GetMesh())
		{
			SourceMesh->SetVisibility(true, false);
		}
	}
	ModelMesh->SetVisibility(false);
	bPoseVisible = false;
}

void AMotionWeaverStancePreviewActor::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	SaveTelemetry();
	const bool bWasPoseVisible = bPoseVisible;
	RestoreSourceMesh();
	UE_LOG(LogMotionWeaverStancePreview, Display, TEXT("MW_MODEL_END: inference=%d failures=%d visible=%d"), NumInferences, NumInferenceFailures, bWasPoseVisible);
	Instance.Reset();
	ModelData = nullptr;
	Super::EndPlay(EndPlayReason);
}

void AMotionWeaverStancePreviewActor::SaveTelemetry() const
{
	if (TelemetryRows.Num() <= 1)
	{
		return;
	}
	const FString Folder = FPaths::ProjectSavedDir() / TEXT("MotionWeaver");
	IFileManager::Get().MakeDirectory(*Folder, true);
	const FString Path = Folder / FString::Printf(TEXT("stance_model_%s_%s.csv"), bUseFeedback ? TEXT("feedback") : TEXT("source"),
		*FDateTime::UtcNow().ToString(TEXT("%Y%m%dT%H%M%SZ")));
	if (FFileHelper::SaveStringArrayToFile(TelemetryRows, *Path))
	{
		UE_LOG(LogMotionWeaverStancePreview, Display, TEXT("MW_MODEL_TELEMETRY: rows=%d path=%s"), TelemetryRows.Num() - 1, *Path);
	}
	else
	{
		UE_LOG(LogMotionWeaverStancePreview, Error, TEXT("MW_MODEL_TELEMETRY_FAIL: %s"), *Path);
	}
}
