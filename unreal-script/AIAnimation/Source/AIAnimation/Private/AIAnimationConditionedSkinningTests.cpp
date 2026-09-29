// Copyright ZhaoZining. All Rights Reserved.

// 在 UE 的 NNE 中运行条件模型真实输入，先校验数值，再交给蒙皮场景使用。
#include "Engine/SkeletalMesh.h"
#include "Materials/MaterialInterface.h"
#include "Engine/DirectionalLight.h"
#include "Engine/PointLight.h"
#include "Engine/StaticMesh.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Engine/World.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/PoseableMeshComponent.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Components/StaticMeshComponent.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "ImageUtils.h"
#include "Misc/AutomationTest.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "NNE.h"
#include "NNEModelData.h"
#include "NNERuntimeCPU.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/BufferArchive.h"
#include "Tests/AutomationCommon.h"
#include "UObject/StrongObjectPtr.h"

#if WITH_DEV_AUTOMATION_TESTS
namespace
{
	bool LoadFloatArray(const FString& Path, int32 ExpectedCount, TArray<float>& Values)
	{
		TArray<uint8> Bytes;
		if (!FFileHelper::LoadFileToArray(Bytes, *Path) || Bytes.Num() != ExpectedCount * sizeof(float))
		{
			return false;
		}
		Values.SetNumUninitialized(ExpectedCount);
		FMemory::Memcpy(Values.GetData(), Bytes.GetData(), Bytes.Num());
		return true;
	}

	struct FConditionedNneModel
	{
		TStrongObjectPtr<UNNEModelData> ModelData;
		TSharedPtr<UE::NNE::IModelCPU> Model;
		TSharedPtr<UE::NNE::IModelInstanceCPU> Instance;

		bool Initialize(const FString& Path)
		{
			TArray<uint8> Bytes;
			if (!FFileHelper::LoadFileToArray(Bytes, *Path))
			{
				return false;
			}
			ModelData.Reset(NewObject<UNNEModelData>());
			ModelData->Init(TEXT("onnx"), MakeArrayView(Bytes));
			ModelData->SetTargetRuntimes({ TEXT("NNERuntimeORTCpu") });
			TWeakInterfacePtr<INNERuntimeCPU> Runtime = UE::NNE::GetRuntime<INNERuntimeCPU>(TEXT("NNERuntimeORTCpu"));
			if (!Runtime.IsValid() || Runtime->CanCreateModelCPU(ModelData.Get()) != UE::NNE::EResultStatus::Ok)
			{
				return false;
			}
			Model = Runtime->CreateModelCPU(ModelData.Get());
			Instance = Model ? Model->CreateModelInstanceCPU() : nullptr;
			if (!Instance || Instance->GetInputTensorDescs().Num() != 4 || Instance->GetOutputTensorDescs().Num() != 1)
			{
				return false;
			}
			const TArray<UE::NNE::FTensorShape> Shapes = {
				UE::NNE::FTensorShape::Make({ 1u, 24u, 718u }), UE::NNE::FTensorShape::Make({ 1u, 24u, 7u }),
				UE::NNE::FTensorShape::Make({ 1u, 24u, 711u }), UE::NNE::FTensorShape::Make({ 1u, 24u, 1u })
			};
			return Instance->SetInputTensorShapes(Shapes) == UE::NNE::EResultStatus::Ok
				&& Instance->GetOutputTensorShapes().Num() == 1 && Instance->GetOutputTensorShapes()[0].Volume() == 24 * 711;
		}

		bool Run(const FString& Folder, const FString& ModelName, int32 Step, TArray<float>& Output, double& Milliseconds, double& MaxError) const
		{
			const FString Prefix = Folder / FString::Printf(TEXT("%s_%d_"), *ModelName, Step);
			TArray<float> History, RootPlan, Reference, Mask, Expected;
			if (!LoadFloatArray(Prefix + TEXT("history.f32"), 24 * 718, History)
				|| !LoadFloatArray(Prefix + TEXT("root_plan.f32"), 24 * 7, RootPlan)
				|| !LoadFloatArray(Prefix + TEXT("reference.f32"), 24 * 711, Reference)
				|| !LoadFloatArray(Prefix + TEXT("mask.f32"), 24, Mask)
				|| !LoadFloatArray(Folder / FString::Printf(TEXT("%s_%d_expected.f32"), *ModelName, Step), 24 * 711, Expected))
			{
				return false;
			}
			Output.SetNumZeroed(24 * 711);
			const TArray<UE::NNE::FTensorBindingCPU> Inputs = {
				{ History.GetData(), uint64(History.Num()) * sizeof(float) }, { RootPlan.GetData(), uint64(RootPlan.Num()) * sizeof(float) },
				{ Reference.GetData(), uint64(Reference.Num()) * sizeof(float) }, { Mask.GetData(), uint64(Mask.Num()) * sizeof(float) }
			};
			const UE::NNE::FTensorBindingCPU Result { Output.GetData(), uint64(Output.Num()) * sizeof(float) };
			const double Start = FPlatformTime::Seconds();
			const UE::NNE::EResultStatus Status = Instance->RunSync(Inputs, MakeArrayView(&Result, 1));
			Milliseconds = (FPlatformTime::Seconds() - Start) * 1000.0;
			if (Status != UE::NNE::EResultStatus::Ok)
			{
				return false;
			}
			MaxError = 0.0;
			for (int32 Index = 0; Index < Output.Num(); ++Index)
			{
				if (!FMath::IsFinite(Output[Index]))
				{
					return false;
				}
				MaxError = FMath::Max(MaxError, FMath::Abs(double(Output[Index]) - Expected[Index]));
			}
			return true;
		}
	};

	struct FConditionedBone
	{
		FName Name;
		int32 ParentIndex = INDEX_NONE;
		int32 MeshIndex = INDEX_NONE;
		FQuat ReferenceRotation;
	};

	bool LoadSkeleton(const FString& Path, const USkeletalMesh& Mesh, TArray<FConditionedBone>& Bones)
	{
		FString Json;
		TSharedPtr<FJsonObject> Object;
		if (!FFileHelper::LoadFileToString(Json, *Path) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Object) || !Object.IsValid())
		{
			return false;
		}
		const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
		if (!Object->TryGetArrayField(TEXT("bones"), Values) || Values->Num() != 79)
		{
			return false;
		}
		const FReferenceSkeleton& ReferenceSkeleton = Mesh.GetRefSkeleton();
		for (const TSharedPtr<FJsonValue>& Value : *Values)
		{
			const TSharedPtr<FJsonObject> BoneObject = Value->AsObject();
			if (!BoneObject.IsValid())
			{
				return false;
			}
			FConditionedBone Bone;
			FString Name;
			if (!BoneObject->TryGetStringField(TEXT("name"), Name) || !BoneObject->TryGetNumberField(TEXT("parent"), Bone.ParentIndex))
			{
				return false;
			}
			Bone.Name = FName(Name);
			Bone.MeshIndex = ReferenceSkeleton.FindBoneIndex(Bone.Name);
			const TArray<TSharedPtr<FJsonValue>>* Quaternion = nullptr;
			if (Bone.MeshIndex == INDEX_NONE || !BoneObject->TryGetArrayField(TEXT("rotation"), Quaternion) || Quaternion->Num() != 4)
			{
				return false;
			}
			Bone.ReferenceRotation = FQuat((*Quaternion)[0]->AsNumber(), (*Quaternion)[1]->AsNumber(), (*Quaternion)[2]->AsNumber(), (*Quaternion)[3]->AsNumber());
			if (!Bone.ReferenceRotation.IsNormalized() || (Bone.ParentIndex != INDEX_NONE
				&& (Bone.ParentIndex < 0 || Bone.ParentIndex >= Bones.Num() || ReferenceSkeleton.GetParentIndex(Bone.MeshIndex) != Bones[Bone.ParentIndex].MeshIndex)))
			{
				return false;
			}
			Bones.Add(Bone);
		}
		return Bones.Num() == 79;
	}

	FVector DataToUnreal(const FVector& Value)
	{
		return FVector(Value.Z, -Value.X, Value.Y);
	}

	FQuat DataToUnreal(const FQuat& Value)
	{
		return FQuat(-Value.Z, Value.X, -Value.Y, Value.W).GetNormalized();
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

	bool ApplyPose(UPoseableMeshComponent& Mesh, TConstArrayView<FConditionedBone> Bones, TConstArrayView<float> Mean,
		TConstArrayView<float> Std, TConstArrayView<float> Pose, int32 Frame)
	{
		TArray<FTransform, TInlineAllocator<79>> Components;
		Components.SetNum(Bones.Num());
		for (int32 Index = 0; Index < Bones.Num(); ++Index)
		{
			const int32 Base = (Frame * Bones.Num() + Index) * 9;
			const FVector DataPosition(Pose[Base] * Std[Index * 3] + Mean[Index * 3],
				Pose[Base + 1] * Std[Index * 3 + 1] + Mean[Index * 3 + 1], Pose[Base + 2] * Std[Index * 3 + 2] + Mean[Index * 3 + 2]);
			const FQuat Rotation = DataToUnreal(DecodeRotation(Pose.GetData() + Base + 3)) * Bones[Index].ReferenceRotation;
			const FTransform Component(Rotation.GetNormalized(), DataToUnreal(DataPosition) * 100.0);
			if (Component.ContainsNaN())
			{
				return false;
			}
			Components[Index] = Component;
			const FTransform Parent = Bones[Index].ParentIndex == INDEX_NONE ? FTransform::Identity : Components[Bones[Index].ParentIndex];
			Mesh.BoneSpaceTransforms[Bones[Index].MeshIndex] = Component.GetRelativeTransform(Parent);
		}
		Mesh.MarkRefreshTransformDirty();
		return true;
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAIAnimationConditionedSkinningTest, "AIAnimation.Lab.ConditionedSkinning", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FAIAnimationConditionedSkinningTest::RunTest(const FString& Parameters)
{
	const FString FixtureDir = FPlatformMisc::GetEnvironmentVariable(TEXT("AIANIMATION_CONDITIONED_FIXTURES"));
	const FString BaselinePath = FPlatformMisc::GetEnvironmentVariable(TEXT("AIANIMATION_CONDITIONED_BASELINE_ONNX"));
	const FString CandidatePath = FPlatformMisc::GetEnvironmentVariable(TEXT("AIANIMATION_CONDITIONED_CANDIDATE_ONNX"));
	if (!TestTrue(TEXT("明确提供测试数据和两个 ONNX 模型"), !FixtureDir.IsEmpty() && !BaselinePath.IsEmpty() && !CandidatePath.IsEmpty()))
	{
		return false;
	}
	USkeletalMesh* Mesh = LoadObject<USkeletalMesh>(nullptr, TEXT("/Game/Characters/UEFN_Mannequin/Meshes/SKM_UEFN_Mannequin.SKM_UEFN_Mannequin"));
	if (!TestNotNull(TEXT("加载原版 UEFN Mannequin 蒙皮网格"), Mesh))
	{
		return false;
	}
	FConditionedNneModel Baseline;
	FConditionedNneModel Candidate;
	if (!TestTrue(TEXT("NNE 加载旧权重"), Baseline.Initialize(BaselinePath)) || !TestTrue(TEXT("NNE 加载新权重"), Candidate.Initialize(CandidatePath)))
	{
		return false;
	}
	const FString OutputDir = FPlatformMisc::GetEnvironmentVariable(TEXT("AIANIMATION_CONDITIONED_RENDER_OUTPUT"));
	TArray<FString> Scenarios;
	const FString Selection = FPlatformMisc::GetEnvironmentVariable(TEXT("AIANIMATION_CONDITIONED_SCENARIOS"));
	if (Selection.IsEmpty())
	{
		Scenarios.Add(TEXT("run"));
	}
	else
	{
		Selection.ParseIntoArray(Scenarios, TEXT(","), true);
	}
	const FString MaxFramesText = FPlatformMisc::GetEnvironmentVariable(TEXT("AIANIMATION_CONDITIONED_MAX_FRAMES"));
	const int32 MaxFrames = MaxFramesText.IsEmpty() ? 72 : FMath::Clamp(FCString::Atoi(*MaxFramesText), 1, 72);
	TArray<float> Mean, Std;
	TArray<FConditionedBone> Bones;
	if (!TestTrue(TEXT("统计量与蒙皮骨架契约一致"), LoadFloatArray(FixtureDir / TEXT("mean.f32"), 79 * 3, Mean)
		&& LoadFloatArray(FixtureDir / TEXT("std.f32"), 79 * 3, Std) && LoadSkeleton(FixtureDir / TEXT("skeleton.json"), *Mesh, Bones)))
	{
		return false;
	}
	if (OutputDir.IsEmpty())
	{
		TArray<float> Output;
		double Milliseconds = 0.0;
		double MaxError = 0.0;
		const bool bRan = Baseline.Run(FixtureDir / TEXT("run"), TEXT("baseline"), 0, Output, Milliseconds, MaxError);
		TestTrue(TEXT("NNE 旧权重真实输入"), bRan && MaxError < 0.01);
		UE_LOG(LogTemp, Display, TEXT("AIAnimationConditioned baseline run window 0: %.3f ms; max error %.9f"), Milliseconds, MaxError);
		const bool bRanCandidate = Candidate.Run(FixtureDir / TEXT("run"), TEXT("candidate"), 0, Output, Milliseconds, MaxError);
		TestTrue(TEXT("NNE 新权重真实输入"), bRanCandidate && MaxError < 0.01);
		UE_LOG(LogTemp, Display, TEXT("AIAnimationConditioned candidate run window 0: %.3f ms; max error %.9f"), Milliseconds, MaxError);
		return !HasAnyErrors();
	}

	FTestWorldWrapper WorldWrapper;
	if (!TestTrue(TEXT("创建蒙皮渲染测试 World"), WorldWrapper.CreateTestWorld(EWorldType::Game)))
	{
		return false;
	}
	UWorld* World = WorldWrapper.GetTestWorld();
	AActor* Floor = World->SpawnActor<AActor>();
	UStaticMeshComponent* FloorMesh = NewObject<UStaticMeshComponent>(Floor);
	Floor->SetRootComponent(FloorMesh);
	FloorMesh->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")));
	FloorMesh->SetCollisionProfileName(TEXT("NoCollision"));
	FloorMesh->RegisterComponent();
	Floor->SetActorLocation(FVector(0, 0, -5));
	Floor->SetActorScale3D(FVector(30, 30, 0.1));
	ADirectionalLight* Sun = World->SpawnActor<ADirectionalLight>();
	Sun->SetActorRotation(FRotator(-50, -35, 0));
	Sun->GetLightComponent()->SetIntensity(1000.0f);
	APointLight* Fill = World->SpawnActor<APointLight>(FVector(200, 0, 300), FRotator::ZeroRotator);
	Fill->GetLightComponent()->SetIntensity(10000.0f);
	CastChecked<UPointLightComponent>(Fill->GetLightComponent())->SetAttenuationRadius(1500.0f);
	UPoseableMeshComponent* Skins[2] = {};
	AActor* Characters[2] = {};
	UMaterialInterface* ValidationMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	if (!TestNotNull(TEXT("加载中性蒙皮可视材质"), ValidationMaterial))
	{
		return false;
	}
	for (int32 Index = 0; Index < 2; ++Index)
	{
		Characters[Index] = World->SpawnActor<AActor>();
		Skins[Index] = NewObject<UPoseableMeshComponent>(Characters[Index]);
		Characters[Index]->SetRootComponent(Skins[Index]);
		Skins[Index]->SetSkinnedAssetAndUpdate(Mesh);
		for (int32 MaterialIndex = 0; MaterialIndex < Skins[Index]->GetNumMaterials(); ++MaterialIndex)
		{
			Skins[Index]->SetMaterial(MaterialIndex, ValidationMaterial);
		}
		Skins[Index]->RegisterComponent();
		if (!TestEqual(TEXT("蒙皮组件骨骼数"), Skins[Index]->BoneSpaceTransforms.Num(), Mesh->GetRefSkeleton().GetNum()))
		{
			return false;
		}
	}
	AActor* Camera = World->SpawnActor<AActor>();
	USceneCaptureComponent2D* Capture = NewObject<USceneCaptureComponent2D>(Camera);
	Camera->SetRootComponent(Capture);
	Capture->bCaptureEveryFrame = false;
	Capture->bCaptureOnMovement = false;
	Capture->CaptureSource = ESceneCaptureSource::SCS_BaseColor;
	Capture->FOVAngle = 58.0f;
	UTextureRenderTarget2D* Target = NewObject<UTextureRenderTarget2D>(Camera);
	Target->InitAutoFormat(960, 540);
	Target->UpdateResourceImmediate(true);
	Capture->TextureTarget = Target;
	Capture->RegisterComponent();
	if (!TestTrue(TEXT("蒙皮渲染 World 开始 Play"), WorldWrapper.BeginPlayInTestWorld()))
	{
		return false;
	}
	for (const FString& Scenario : Scenarios)
	{
		if (Scenario != TEXT("walk") && Scenario != TEXT("run") && Scenario != TEXT("crouch") && Scenario != TEXT("stand_to_crouch"))
		{
			AddError(FString::Printf(TEXT("未知场景：%s"), *Scenario));
			return false;
		}
		const FString Folder = FixtureDir / Scenario;
		TArray<float> Roots, BaselinePose, CandidatePose;
		if (!TestTrue(TEXT("读取 CMC 已执行 Root"), LoadFloatArray(Folder / TEXT("accepted_root.f32"), 72 * 7, Roots)))
		{
			return false;
		}
		for (int32 Step = 0; Step < 3; ++Step)
		{
			TArray<float> Output;
			double Milliseconds = 0.0;
			double MaxError = 0.0;
			if (!TestTrue(TEXT("旧模型 UE NNE 连续窗口"), Baseline.Run(Folder, TEXT("baseline"), Step, Output, Milliseconds, MaxError)) || !TestTrue(TEXT("旧模型 UE 数值对照"), MaxError < 0.01))
			{
				return false;
			}
			BaselinePose.Append(Output);
			UE_LOG(LogTemp, Display, TEXT("AIAnimationConditioned %s baseline step %d: %.3f ms; max error %.9f"), *Scenario, Step, Milliseconds, MaxError);
			if (!TestTrue(TEXT("新模型 UE NNE 连续窗口"), Candidate.Run(Folder, TEXT("candidate"), Step, Output, Milliseconds, MaxError)) || !TestTrue(TEXT("新模型 UE 数值对照"), MaxError < 0.01))
			{
				return false;
			}
			CandidatePose.Append(Output);
			UE_LOG(LogTemp, Display, TEXT("AIAnimationConditioned %s candidate step %d: %.3f ms; max error %.9f"), *Scenario, Step, Milliseconds, MaxError);
		}
		const FString FrameDir = OutputDir / Scenario;
		IFileManager::Get().MakeDirectory(*FrameDir, true);
		const FVector InitialRoot(Roots[0], Roots[1], Roots[2]);
		const FQuat InitialRotation = DataToUnreal(FQuat(Roots[3], Roots[4], Roots[5], Roots[6]));
		for (int32 Frame = 0; Frame < MaxFrames; ++Frame)
		{
			const float* Row = Roots.GetData() + Frame * 7;
			const FVector Motion = DataToUnreal(FVector(Row[0], Row[1], Row[2]) - InitialRoot) * 100.0;
			const FQuat Direction = DataToUnreal(FQuat(Row[3], Row[4], Row[5], Row[6])) * InitialRotation.Inverse();
			for (int32 Index = 0; Index < 2; ++Index)
			{
				UPoseableMeshComponent* Skin = Skins[Index];
				Skin->BoneSpaceTransforms = Mesh->GetRefSkeleton().GetRefBonePose();
				if (!TestTrue(TEXT("UE 输出构成有效蒙皮姿态"), ApplyPose(*Skin, Bones, Mean, Std, Index == 0 ? TConstArrayView<float>(BaselinePose) : TConstArrayView<float>(CandidatePose), Frame)))
				{
					return false;
				}
				Characters[Index]->SetActorLocationAndRotation(Motion + FVector(0, Index == 0 ? -115.0 : 115.0, 0), Direction);
			}
			const FVector LookAt = Motion + FVector(0, 0, 95);
			const FVector CameraLocation = Motion + FVector(-430, -70, 185);
			Camera->SetActorLocationAndRotation(CameraLocation, (LookAt - CameraLocation).Rotation());
			if (!WorldWrapper.TickTestWorld(1.0f / 30.0f))
			{
				WorldWrapper.ForwardErrorMessages(this);
				return false;
			}
			Capture->CaptureScene();
			FBufferArchive Png;
			const FString Filename = FrameDir / FString::Printf(TEXT("frame_%03d.png"), Frame);
			if (!TestTrue(TEXT("保存 UE 蒙皮画面"), FImageUtils::ExportRenderTarget2DAsPNG(Target, Png) && FFileHelper::SaveArrayToFile(Png, *Filename)))
			{
				return false;
			}
		}
		UE_LOG(LogTemp, Display, TEXT("AIAnimationConditioned UE skinned %s frames=%d path=%s"), *Scenario, MaxFrames, *FrameDir);
	}
	WorldWrapper.ForwardErrorMessages(this);
	return !HasAnyErrors();
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAIAnimationRootPoseFourWayTest, "AIAnimation.Lab.RootPoseFourWay", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FAIAnimationRootPoseFourWayTest::RunTest(const FString& Parameters)
{
	const FString FixtureDir = FPlatformMisc::GetEnvironmentVariable(TEXT("AIANIMATION_ROOT_POSE_FIXTURES"));
	const FString ModelPath = FPlatformMisc::GetEnvironmentVariable(TEXT("AIANIMATION_ROOT_POSE_CANDIDATE_ONNX"));
	const FString OutputDir = FPlatformMisc::GetEnvironmentVariable(TEXT("AIANIMATION_ROOT_POSE_RENDER_OUTPUT"));
	if (!TestTrue(TEXT("明确提供四路对照输入和输出"), !FixtureDir.IsEmpty() && !ModelPath.IsEmpty() && !OutputDir.IsEmpty()))
	{
		return false;
	}
	USkeletalMesh* Mesh = LoadObject<USkeletalMesh>(nullptr, TEXT("/Game/Characters/UEFN_Mannequin/Meshes/SKM_UEFN_Mannequin.SKM_UEFN_Mannequin"));
	UMaterialInterface* ValidationMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	if (!TestNotNull(TEXT("加载 UEFN Mannequin"), Mesh) || !TestNotNull(TEXT("加载中性验证材质"), ValidationMaterial))
	{
		return false;
	}
	FConditionedNneModel Model;
	if (!TestTrue(TEXT("加载新权重 NNE 模型"), Model.Initialize(ModelPath)))
	{
		return false;
	}
	TArray<float> Mean, Std;
	TArray<FConditionedBone> Bones;
	if (!TestTrue(TEXT("四路对照骨架契约一致"), LoadFloatArray(FixtureDir / TEXT("mean.f32"), 79 * 3, Mean)
		&& LoadFloatArray(FixtureDir / TEXT("std.f32"), 79 * 3, Std) && LoadSkeleton(FixtureDir / TEXT("skeleton.json"), *Mesh, Bones)))
	{
		return false;
	}
	const FName FootNames[] = { TEXT("foot_l"), TEXT("ball_l"), TEXT("foot_r"), TEXT("ball_r") };
	int32 FootIndices[4] = { INDEX_NONE, INDEX_NONE, INDEX_NONE, INDEX_NONE };
	for (int32 Index = 0; Index < Bones.Num(); ++Index)
	{
		for (int32 Foot = 0; Foot < 4; ++Foot)
		{
			if (Bones[Index].Name == FootNames[Foot])
			{
				FootIndices[Foot] = Index;
			}
		}
	}
	if (!TestTrue(TEXT("四个脚/脚掌骨骼均存在"), FootIndices[0] >= 0 && FootIndices[1] >= 0 && FootIndices[2] >= 0 && FootIndices[3] >= 0))
	{
		return false;
	}
	FTestWorldWrapper WorldWrapper;
	if (!TestTrue(TEXT("创建四路蒙皮测试 World"), WorldWrapper.CreateTestWorld(EWorldType::Game)))
	{
		return false;
	}
	UWorld* World = WorldWrapper.GetTestWorld();
	AActor* Floor = World->SpawnActor<AActor>();
	UStaticMeshComponent* FloorMesh = NewObject<UStaticMeshComponent>(Floor);
	Floor->SetRootComponent(FloorMesh);
	FloorMesh->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")));
	FloorMesh->SetCollisionProfileName(TEXT("NoCollision"));
	FloorMesh->RegisterComponent();
	Floor->SetActorLocation(FVector(0, 0, -5));
	Floor->SetActorScale3D(FVector(50, 50, 0.1));
	AActor* Character = World->SpawnActor<AActor>();
	UPoseableMeshComponent* Skin = NewObject<UPoseableMeshComponent>(Character);
	Character->SetRootComponent(Skin);
	Skin->SetSkinnedAssetAndUpdate(Mesh);
	for (int32 MaterialIndex = 0; MaterialIndex < Skin->GetNumMaterials(); ++MaterialIndex)
	{
		Skin->SetMaterial(MaterialIndex, ValidationMaterial);
	}
	Skin->RegisterComponent();
	AActor* Camera = World->SpawnActor<AActor>();
	USceneCaptureComponent2D* Capture = NewObject<USceneCaptureComponent2D>(Camera);
	Camera->SetRootComponent(Capture);
	Capture->bCaptureEveryFrame = false;
	Capture->bCaptureOnMovement = false;
	Capture->CaptureSource = ESceneCaptureSource::SCS_BaseColor;
	Capture->FOVAngle = 58.0f;
	UTextureRenderTarget2D* Target = NewObject<UTextureRenderTarget2D>(Camera);
	Target->InitAutoFormat(640, 360);
	Target->UpdateResourceImmediate(true);
	Capture->TextureTarget = Target;
	Capture->RegisterComponent();
	if (!TestTrue(TEXT("四路蒙皮 World 开始 Play"), WorldWrapper.BeginPlayInTestWorld()))
	{
		return false;
	}

	const FString Scenarios[] = { TEXT("walk"), TEXT("run"), TEXT("crouch") };
	const FString LaneNames[] = { TEXT("source_source"), TEXT("source_cmc"), TEXT("model_plan"), TEXT("model_cmc") };
	FString BoneCsv = TEXT("scenario,lane,frame,bone,world_x_cm,world_y_cm,world_z_cm,expected_x_cm,expected_y_cm,expected_z_cm,error_cm\n");
	double MaxBoneErrorCm = 0.0;
	for (const FString& Scenario : Scenarios)
	{
		const FString Folder = FixtureDir / Scenario;
		TArray<float> SourcePose, SourceRoot, AcceptedRoot, PlannedRoot, GeneratedPose;
		if (!TestTrue(TEXT("读取四路对照姿态与 Root"), LoadFloatArray(Folder / TEXT("source_pose.f32"), 72 * 79 * 9, SourcePose)
			&& LoadFloatArray(Folder / TEXT("source_root.f32"), 72 * 7, SourceRoot)
			&& LoadFloatArray(Folder / TEXT("accepted_root.f32"), 72 * 7, AcceptedRoot)
			&& LoadFloatArray(Folder / TEXT("command_plan.f32"), 72 * 7, PlannedRoot)))
		{
			return false;
		}
		for (int32 Step = 0; Step < 3; ++Step)
		{
			TArray<float> Output;
			double Milliseconds = 0.0;
			double MaxError = 0.0;
			if (!TestTrue(TEXT("UE NNE 在匹配 Root 输入下推理"), Model.Run(Folder, TEXT("candidate"), Step, Output, Milliseconds, MaxError))
				|| !TestTrue(TEXT("四路测试与 Python ORT 数值一致"), MaxError < 0.01))
			{
				return false;
			}
			GeneratedPose.Append(Output);
			UE_LOG(LogTemp, Display, TEXT("AIAnimationFourWay %s step %d: %.3f ms; max error %.9f"), *Scenario, Step, Milliseconds, MaxError);
		}
		const TArray<float>* Poses[] = { &SourcePose, &SourcePose, &GeneratedPose, &GeneratedPose };
		const TArray<float>* Roots[] = { &SourceRoot, &AcceptedRoot, &PlannedRoot, &AcceptedRoot };
		for (int32 Lane = 0; Lane < 4; ++Lane)
		{
			const FString FrameDir = OutputDir / Scenario / LaneNames[Lane];
			IFileManager::Get().MakeDirectory(*FrameDir, true);
			const TArray<float>& Root = *Roots[Lane];
			const FVector InitialPosition(Root[0], Root[1], Root[2]);
			const FQuat InitialRotation = DataToUnreal(FQuat(Root[3], Root[4], Root[5], Root[6]));
			for (int32 Frame = 0; Frame < 72; ++Frame)
			{
				const float* Row = Root.GetData() + Frame * 7;
				const FVector Motion = DataToUnreal(FVector(Row[0], Row[1], Row[2]) - InitialPosition) * 100.0;
				const FQuat Direction = DataToUnreal(FQuat(Row[3], Row[4], Row[5], Row[6])) * InitialRotation.Inverse();
				Skin->BoneSpaceTransforms = Mesh->GetRefSkeleton().GetRefBonePose();
				if (!TestTrue(TEXT("四路姿态构成有效蒙皮"), ApplyPose(*Skin, Bones, Mean, Std, *Poses[Lane], Frame)))
				{
				return false;
				}
				Character->SetActorLocationAndRotation(Motion, Direction);
				const FVector CameraLocation = Motion + FVector(-420, -65, 180);
				const FVector LookAt = Motion + FVector(0, 0, 95);
				Camera->SetActorLocationAndRotation(CameraLocation, (LookAt - CameraLocation).Rotation());
				if (!WorldWrapper.TickTestWorld(1.0f / 30.0f))
				{
				WorldWrapper.ForwardErrorMessages(this);
				return false;
				}
				for (int32 Foot = 0; Foot < 4; ++Foot)
				{
					const int32 Bone = FootIndices[Foot];
					const int32 Base = (Frame * Bones.Num() + Bone) * 9;
					const TArray<float>& Pose = *Poses[Lane];
					const FVector DataPosition(Pose[Base] * Std[Bone * 3] + Mean[Bone * 3],
						Pose[Base + 1] * Std[Bone * 3 + 1] + Mean[Bone * 3 + 1], Pose[Base + 2] * Std[Bone * 3 + 2] + Mean[Bone * 3 + 2]);
					const FVector Expected = Character->GetActorTransform().TransformPosition(DataToUnreal(DataPosition) * 100.0);
					const FVector Actual = Skin->GetBoneLocationByName(FootNames[Foot], EBoneSpaces::WorldSpace);
					const double ErrorCm = FVector::Distance(Expected, Actual);
					MaxBoneErrorCm = FMath::Max(MaxBoneErrorCm, ErrorCm);
					BoneCsv += FString::Printf(TEXT("%s,%s,%d,%s,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f\n"),
						*Scenario, *LaneNames[Lane], Frame, *FootNames[Foot].ToString(), Actual.X, Actual.Y, Actual.Z,
						Expected.X, Expected.Y, Expected.Z, ErrorCm);
				}
				Capture->CaptureScene();
				FBufferArchive Png;
				const FString Filename = FrameDir / FString::Printf(TEXT("frame_%03d.png"), Frame);
				if (!TestTrue(TEXT("保存四路 UE 蒙皮画面"), FImageUtils::ExportRenderTarget2DAsPNG(Target, Png) && FFileHelper::SaveArrayToFile(Png, *Filename)))
				{
					return false;
				}
			}
		}
		UE_LOG(LogTemp, Display, TEXT("AIAnimationFourWay UE skinned %s: 4 lanes x 72 frames"), *Scenario);
	}
	IFileManager::Get().MakeDirectory(*OutputDir, true);
	if (!TestTrue(TEXT("保存 UE 脚骨世界坐标"), FFileHelper::SaveStringToFile(BoneCsv, *(OutputDir / TEXT("bone_readback.csv")))))
	{
		return false;
	}
	TestTrue(TEXT("UE 读回脚骨与模型位置一致，误差小于 0.1 cm"), MaxBoneErrorCm < 0.1);
	UE_LOG(LogTemp, Display, TEXT("AIAnimationFourWay max skinned foot-bone readback error %.6f cm"), MaxBoneErrorCm);
	WorldWrapper.ForwardErrorMessages(this);
	return !HasAnyErrors();
}
#endif
