// Copyright ZhaoZining. All Rights Reserved.

// 生成可复现的本地测试资产，原始 GASP 动画图与地图保持为对照来源。
#include "AIAnimationPrepareCommandlet.h"
#include "AIAnimationBenchmark.h"
#include "AIAnimationModel.h"
#include "AnimGraphNode_AIAnimation.h"
#include "AnimGraphNode_Root.h"
#include "Animation/AnimBlueprint.h"
#include "Animation/AnimSequence.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Async/Async.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "FileHelpers.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/WorldSettings.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "NNEModelData.h"
#include "NNE.h"
#include "NNERuntimeGPU.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/SavePackage.h"

THIRD_PARTY_INCLUDES_START
#include <openssl/sha.h>
THIRD_PARTY_INCLUDES_END

namespace
{
	struct FAIAnimationImportContract
	{
		FString TrainingSignature;
		FString ModelSha256;
		int32 WindowFrames = 0;
		float SampleRate = 0.0f;
		FName RootBone;
		TArray<FAIAnimationBone> Bones;
		TArray<FString> ValidationAssets;
	};

	bool IsSha256(const FString& Value)
	{
		if (Value.Len() != 64)
		{
			return false;
		}
		for (const TCHAR Character : Value)
		{
			if (!FChar::IsHexDigit(Character))
			{
				return false;
			}
		}
		return true;
	}

	bool ReadReferenceTransform(const TSharedPtr<FJsonObject>& Object, FTransform& OutTransform)
	{
		const TArray<TSharedPtr<FJsonValue>>* Position = nullptr;
		const TArray<TSharedPtr<FJsonValue>>* Rotation = nullptr;
		if (!Object.IsValid() || !Object->TryGetArrayField(TEXT("position"), Position) || !Object->TryGetArrayField(TEXT("rotation"), Rotation) || Position->Num() != 3 || Rotation->Num() != 4)
		{
			return false;
		}
		double PositionValues[3];
		double RotationValues[4];
		for (int32 Index = 0; Index < UE_ARRAY_COUNT(PositionValues); ++Index)
		{
			const TSharedPtr<FJsonValue>& Value = (*Position)[Index];
			if (!Value.IsValid() || !Value->TryGetNumber(PositionValues[Index]) || !FMath::IsFinite(PositionValues[Index]))
			{
				return false;
			}
		}
		for (int32 Index = 0; Index < UE_ARRAY_COUNT(RotationValues); ++Index)
		{
			const TSharedPtr<FJsonValue>& Value = (*Rotation)[Index];
			if (!Value.IsValid() || !Value->TryGetNumber(RotationValues[Index]) || !FMath::IsFinite(RotationValues[Index]))
			{
				return false;
			}
		}
		const FQuat Quaternion(RotationValues[0], RotationValues[1], RotationValues[2], RotationValues[3]);
		if (Quaternion.SizeSquared() <= SMALL_NUMBER)
		{
			return false;
		}
		OutTransform = FTransform(Quaternion.GetNormalized(), FVector(PositionValues[0], PositionValues[1], PositionValues[2]));
		return !OutTransform.ContainsNaN();
	}

	bool ReadImportContract(const TSharedPtr<FJsonObject>& Manifest, FAIAnimationImportContract& OutContract, FString& OutError)
	{
		FString Format;
		FString TrainingContract;
		FString RootBone;
		double WindowFrames = 0.0;
		double SampleRate = 0.0;
		if (!Manifest.IsValid() || !Manifest->TryGetStringField(TEXT("format"), Format) || Format != TEXT("ai_animation_ue_pose_onnx_v1")
			|| !Manifest->TryGetStringField(TEXT("training_contract"), TrainingContract) || TrainingContract != TEXT("pose_only_root_authoritative")
			|| !Manifest->TryGetStringField(TEXT("training_signature"), OutContract.TrainingSignature) || !IsSha256(OutContract.TrainingSignature)
			|| !Manifest->TryGetStringField(TEXT("onnx_sha256"), OutContract.ModelSha256) || !IsSha256(OutContract.ModelSha256)
			|| !Manifest->TryGetStringField(TEXT("root_bone"), RootBone) || RootBone.IsEmpty()
			|| !Manifest->TryGetNumberField(TEXT("window_frames"), WindowFrames) || !FMath::IsFinite(WindowFrames) || !FMath::IsNearlyEqual(WindowFrames, FMath::RoundToDouble(WindowFrames))
			|| !Manifest->TryGetNumberField(TEXT("fps"), SampleRate) || !FMath::IsFinite(SampleRate) || SampleRate <= 0.0)
		{
			OutError = TEXT("manifest 的固定契约字段缺失或不合法。");
			return false;
		}
		OutContract.WindowFrames = int32(WindowFrames);
		OutContract.SampleRate = float(SampleRate);
		OutContract.RootBone = FName(RootBone);
		if (OutContract.RootBone.IsNone() || OutContract.WindowFrames < 8 || OutContract.WindowFrames > 64 || OutContract.WindowFrames % 4)
		{
			OutError = TEXT("manifest 的 Root、窗口或采样率超出模型契约。");
			return false;
		}

		const TArray<TSharedPtr<FJsonValue>>* BoneValues = nullptr;
		if (!Manifest->TryGetArrayField(TEXT("bones"), BoneValues) || BoneValues->IsEmpty() || BoneValues->Num() > 512)
		{
			OutError = TEXT("manifest 缺少有效的骨骼数组。");
			return false;
		}
		TSet<FName> BoneNames;
		OutContract.Bones.Reserve(BoneValues->Num());
		for (int32 Index = 0; Index < BoneValues->Num(); ++Index)
		{
			const TSharedPtr<FJsonObject> BoneObject = (*BoneValues)[Index].IsValid() ? (*BoneValues)[Index]->AsObject() : nullptr;
			FAIAnimationBone Bone;
			FString BoneName;
			if (!BoneObject.IsValid() || !BoneObject->TryGetStringField(TEXT("name"), BoneName) || BoneName.IsEmpty() || !BoneObject->TryGetNumberField(TEXT("parent"), Bone.ParentIndex)
				|| !ReadReferenceTransform(BoneObject, Bone.ReferenceTransform))
			{
				OutError = FString::Printf(TEXT("manifest 的第 %d 个骨骼字段不合法。"), Index);
				return false;
			}
			Bone.Name = FName(BoneName);
			if (Bone.Name.IsNone() || Bone.Name == OutContract.RootBone || BoneNames.Contains(Bone.Name)
				|| (Index == 0 ? Bone.ParentIndex != INDEX_NONE : Bone.ParentIndex < 0 || Bone.ParentIndex >= Index))
			{
				OutError = FString::Printf(TEXT("manifest 的第 %d 个骨骼拓扑不合法。"), Index);
				return false;
			}
			BoneNames.Add(Bone.Name);
			OutContract.Bones.Add(MoveTemp(Bone));
		}

		const TArray<TSharedPtr<FJsonValue>>* ValidationValues = nullptr;
		if (!Manifest->TryGetArrayField(TEXT("validation"), ValidationValues) || ValidationValues->IsEmpty())
		{
			OutError = TEXT("manifest 缺少验证动画。");
			return false;
		}
		OutContract.ValidationAssets.Reserve(ValidationValues->Num());
		for (const TSharedPtr<FJsonValue>& Value : *ValidationValues)
		{
			const TSharedPtr<FJsonObject> Validation = Value.IsValid() ? Value->AsObject() : nullptr;
			FString Asset;
			if (!Validation.IsValid() || !Validation->TryGetStringField(TEXT("asset"), Asset) || Asset.IsEmpty())
			{
				OutError = TEXT("manifest 的验证动画字段不合法。");
				return false;
			}
			OutContract.ValidationAssets.Add(MoveTemp(Asset));
		}
		return true;
	}

	bool ValidateGpuModel(UAIAnimationModel* Asset, const FString& Folder)
	{
		TWeakInterfacePtr<INNERuntimeGPU> Runtime = UE::NNE::GetRuntime<INNERuntimeGPU>(TEXT("NNERuntimeORTDml"));
		if (!Runtime.IsValid())
		{
			return false;
		}
		TSharedPtr<UE::NNE::IModelGPU> Model = Runtime->CreateModelGPU(Asset->ModelData);
		TSharedPtr<UE::NNE::IModelInstanceGPU> Instance = Model ? Model->CreateModelInstanceGPU() : nullptr;
		TArray<uint8> Inputs;
		TArray<uint8> Expected;
		if (!Instance || !FFileHelper::LoadFileToArray(Inputs, *(Folder / TEXT("validation_inputs.bin")))
			|| !FFileHelper::LoadFileToArray(Expected, *(Folder / TEXT("validation_expected.bin"))))
		{
			return false;
		}
		const TArray<uint32> Dimensions = { 1u, uint32(Asset->WindowFrames + 1), uint32(Asset->Bones.Num()), 12u };
		const TArray<UE::NNE::FTensorShape> Shapes = { UE::NNE::FTensorShape::Make(Dimensions) };
		if (Instance->SetInputTensorShapes(Shapes) != UE::NNE::EResultStatus::Ok)
		{
			return false;
		}
		const int32 InputValues = (Asset->WindowFrames + 1) * Asset->Bones.Num() * 12;
		const int32 OutputValues = Asset->WindowFrames * Asset->Bones.Num() * 12;
		const int32 Count = Inputs.Num() / (InputValues * sizeof(float));
		if (Count < 1 || Inputs.Num() != Count * InputValues * sizeof(float) || Expected.Num() != Count * OutputValues * sizeof(float))
		{
			return false;
		}
		const double MaxError = Async(EAsyncExecution::ThreadPool, [Instance, &Inputs, &Expected, InputValues, OutputValues, Count]()
		{
			TArray<float> Output;
			Output.SetNumZeroed(OutputValues);
			double Error = 0.0;
			for (int32 Index = 0; Index < Count; ++Index)
			{
				UE::NNE::FTensorBindingCPU InputBinding { Inputs.GetData() + Index * InputValues * sizeof(float), uint64(InputValues) * sizeof(float) };
				UE::NNE::FTensorBindingCPU OutputBinding { Output.GetData(), uint64(OutputValues) * sizeof(float) };
				if (Instance->RunSync(MakeArrayView(&InputBinding, 1), MakeArrayView(&OutputBinding, 1)) != UE::NNE::EResultStatus::Ok)
				{
					return -1.0;
				}
				const float* Reference = reinterpret_cast<const float*>(Expected.GetData()) + Index * OutputValues;
				for (int32 Element = 0; Element < OutputValues; ++Element)
				{
					if (!FMath::IsFinite(Output[Element]))
					{
						return -1.0;
					}
					Error = FMath::Max(Error, double(FMath::Abs(Output[Element] - Reference[Element])));
				}
			}
			return Error;
		}).Get();
		const bool bPassed = MaxError >= 0.0 && MaxError < 0.01;
		const FString Report = FString::Printf(TEXT("{\"backend\":\"NNERuntimeORTDml\",\"samples\":%d,\"max_abs_error\":%.9f,\"passed\":%s}"), Count, MaxError, bPassed ? TEXT("true") : TEXT("false"));
		FFileHelper::SaveStringToFile(Report, *(Folder / TEXT("gpu_validation.json")), FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
		UE_LOG(LogTemp, Display, TEXT("AIAnimation GPU validation: %s"), *Report);
		return bPassed;
	}

	bool SaveAsset(UObject* Asset)
	{
		UPackage* Package = Asset->GetOutermost();
		Package->MarkPackageDirty();
		FSavePackageArgs Args;
		Args.TopLevelFlags = RF_Public | RF_Standalone;
		const FString Filename = FPackageName::LongPackageNameToFilename(Package->GetName(), FPackageName::GetAssetPackageExtension());
		return UPackage::SavePackage(Package, Asset, *Filename, Args);
	}

	bool CreateGaspGraph(UAIAnimationModel* Model, const FString& AssetRoot)
	{
		UAnimBlueprint* Source = LoadObject<UAnimBlueprint>(nullptr, TEXT("/Game/Blueprints/SandboxCharacter_CMC_ABP.SandboxCharacter_CMC_ABP"));
		if (!Source)
		{
			return false;
		}
		UPackage* Package = CreatePackage(*(AssetRoot / TEXT("ABP_GaspGPU")));
		Package->FullyLoad();
		UAnimBlueprint* Blueprint = DuplicateObject<UAnimBlueprint>(Source, Package, TEXT("ABP_GaspGPU"));
		TArray<UEdGraph*> Graphs;
		Blueprint->GetAllGraphs(Graphs);
		bool bInserted = false;
		for (UEdGraph* Graph : Graphs)
		{
			if (Graph->GetFName() != TEXT("AnimGraph"))
			{
				continue;
			}
			TArray<UAnimGraphNode_Root*> Roots;
			Graph->GetNodesOfClass(Roots);
			for (UAnimGraphNode_Root* Root : Roots)
			{
				UEdGraphPin* ResultPin = Root->FindPin(TEXT("Result"));
				if (!ResultPin || ResultPin->LinkedTo.Num() != 1)
				{
					return false;
				}
				UEdGraphPin* PreviousOutput = ResultPin->LinkedTo[0];
				FGraphNodeCreator<UAnimGraphNode_AIAnimation> Creator(*Graph);
				UAnimGraphNode_AIAnimation* Node = Creator.CreateNode();
				Node->Node.Model = Model;
				Node->NodePosX = Root->NodePosX - 280;
				Node->NodePosY = Root->NodePosY;
				Creator.Finalize();
				UEdGraphPin* SourcePin = Node->FindPin(TEXT("Source"));
				UEdGraphPin* PosePin = nullptr;
				for (UEdGraphPin* Pin : Node->Pins)
				{
					if (Pin->Direction == EGPD_Output)
					{
						PosePin = Pin;
					}
				}
				if (!SourcePin || !PosePin)
				{
					return false;
				}
				ResultPin->BreakAllPinLinks();
				if (!Graph->GetSchema()->TryCreateConnection(PreviousOutput, SourcePin) || !Graph->GetSchema()->TryCreateConnection(PosePin, ResultPin))
				{
					return false;
				}
				bInserted = true;
			}
		}
		if (!bInserted)
		{
			return false;
		}
		FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
		FKismetEditorUtilities::CompileBlueprint(Blueprint);
		FAssetRegistryModule::AssetCreated(Blueprint);
		return Blueprint->Status != BS_Error && SaveAsset(Blueprint);
	}
}

UAIAnimationPrepareCommandlet::UAIAnimationPrepareCommandlet()
{
	IsClient = false;
	IsServer = false;
	IsEditor = true;
	LogToConsole = true;
}

int32 UAIAnimationPrepareCommandlet::Main(const FString& Params)
{
	FString Variant;
	FParse::Value(*Params, TEXT("Variant="), Variant);
	for (const TCHAR Character : Variant)
	{
		if (!FChar::IsAlnum(Character) && Character != TCHAR('_'))
		{
			UE_LOG(LogTemp, Error, TEXT("Variant 只能包含字母、数字或下划线。"));
			return 1;
		}
	}
	const FString AssetRoot = Variant.IsEmpty() ? TEXT("/Game/AIAnimationPreview") : FString(TEXT("/Game/AIAnimationPreview")) / Variant;
	FString Folder;
	if (!FParse::Value(*Params, TEXT("ModelFolder="), Folder))
	{
		UE_LOG(LogTemp, Error, TEXT("需要 -ModelFolder=ONNX 导出目录"));
		return 1;
	}
	FString Json;
	TSharedPtr<FJsonObject> Manifest;
	TArray<uint8> Bytes;
	if (!FFileHelper::LoadFileToString(Json, *(Folder / TEXT("manifest.json"))) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Manifest)
		|| !FFileHelper::LoadFileToArray(Bytes, *(Folder / TEXT("model.onnx"))))
	{
		UE_LOG(LogTemp, Error, TEXT("导出包读取失败。"));
		return 1;
	}
	FAIAnimationImportContract Contract;
	FString ContractError;
	FSHA256Signature Hash;
	if (!ReadImportContract(Manifest, Contract, ContractError))
	{
		UE_LOG(LogTemp, Error, TEXT("导出包契约不匹配：%s"), *ContractError);
		return 1;
	}
	if (!SHA256(Bytes.GetData(), Bytes.Num(), Hash.Signature) || !Hash.ToString().Equals(Contract.ModelSha256, ESearchCase::IgnoreCase))
	{
		UE_LOG(LogTemp, Error, TEXT("导出包 ONNX SHA-256 不匹配。"));
		return 1;
	}
	UPackage* Package = CreatePackage(*(AssetRoot / TEXT("DA_Reconstruction")));
	Package->FullyLoad();
	UAIAnimationModel* Model = NewObject<UAIAnimationModel>(Package, TEXT("DA_Reconstruction"), RF_Public | RF_Standalone);
	Model->ModelData = NewObject<UNNEModelData>(Model, TEXT("Network"));
	Model->ModelData->Init(TEXT("onnx"), MakeArrayView(Bytes));
	const TArray<FString> Runtimes = { TEXT("NNERuntimeORTDml") };
	Model->ModelData->SetTargetRuntimes(Runtimes);
	Model->TrainingSignature = MoveTemp(Contract.TrainingSignature);
	Model->ModelSha256 = MoveTemp(Contract.ModelSha256);
	Model->WindowFrames = Contract.WindowFrames;
	Model->SampleRate = Contract.SampleRate;
	Model->RootBone = Contract.RootBone;
	Model->Bones = MoveTemp(Contract.Bones);
	FAssetRegistryModule::AssetCreated(Model);
	if (FParse::Param(*Params, TEXT("ValidateGPU")) && !ValidateGpuModel(Model, Folder))
	{
		UE_LOG(LogTemp, Error, TEXT("DirectML 与 PyTorch 六组数值对照失败。"));
		return 1;
	}
	if (!SaveAsset(Model) || !CreateGaspGraph(Model, AssetRoot))
	{
		UE_LOG(LogTemp, Error, TEXT("模型保存或 GASP 动画图复制编译失败。"));
		return 1;
	}
	UWorld* World = UEditorLoadingAndSavingUtils::NewBlankMap(false);
	World->GetWorldSettings()->DefaultGameMode = AGameModeBase::StaticClass();
	AAIAnimationBenchmark* Benchmark = World->SpawnActor<AAIAnimationBenchmark>();
	Benchmark->Model = Model;
	Benchmark->CharacterMesh = LoadObject<USkeletalMesh>(nullptr, TEXT("/Game/Characters/UEFN_Mannequin/Meshes/SKM_UEFN_Mannequin.SKM_UEFN_Mannequin"));
	for (const FString& AssetPath : Contract.ValidationAssets)
	{
		UAnimSequence* Animation = LoadObject<UAnimSequence>(nullptr, *AssetPath);
		if (!Animation)
		{
			return 1;
		}
		Benchmark->Animations.Add(Animation);
	}
	AStaticMeshActor* Floor = World->SpawnActor<AStaticMeshActor>();
	Floor->GetStaticMeshComponent()->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")));
	Floor->SetActorLocation(FVector(0, 0, -10));
	Floor->SetActorScale3D(FVector(20, 20, .2));
	ADirectionalLight* Light = World->SpawnActor<ADirectionalLight>();
	Light->SetActorRotation(FRotator(-45, -100, 0));
	Light->GetLightComponent()->SetIntensity(6.0f);
	ADirectionalLight* FillLight = World->SpawnActor<ADirectionalLight>();
	FillLight->SetActorRotation(FRotator(-30, 70, 0));
	FillLight->GetLightComponent()->SetIntensity(3.0f);
	const bool bSaved = UEditorLoadingAndSavingUtils::SaveMap(World, AssetRoot / TEXT("L_ReconstructionBenchmark"));
	UE_LOG(LogTemp, Display, TEXT("AIAnimation prepared: Model=%s MapSaved=%d"), *Model->GetPathName(), bSaved);
	return bSaved && Benchmark->CharacterMesh ? 0 : 1;
}
