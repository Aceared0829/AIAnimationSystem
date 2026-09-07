// Copyright ZhaoZining. All Rights Reserved.

/** 在编辑器主菜单导出选中的动画；保持源资产不变，仅发布完整的数据批次。 */
#include "AILocomotionDatasetSettings.h"
#include "AnimPose.h"
#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "AssetRegistry/AssetData.h"
#include "ContentBrowserModule.h"
#include "IContentBrowserSingleton.h"
#include "Dom/JsonObject.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Guid.h"
#include "Misc/MessageDialog.h"
#include "Misc/Paths.h"
#include "Misc/ScopedSlowTask.h"
#include "Modules/ModuleManager.h"
#include "Serialization/JsonSerializer.h"
#include "ToolMenus.h"

#define LOCTEXT_NAMESPACE "AILocomotionDataset"

namespace
{
	TArray<TSharedPtr<FJsonValue>> Numbers(std::initializer_list<double> Values)
	{
		TArray<TSharedPtr<FJsonValue>> Result;
		for (double Value : Values)
		{
			Result.Add(MakeShared<FJsonValueNumber>(Value));
		}
		return Result;
	}

	bool WriteJson(const FString& Path, const TSharedRef<FJsonObject>& Object)
	{
		FString Text;
		return FJsonSerializer::Serialize(Object, TJsonWriterFactory<>::Create(&Text)) && FFileHelper::SaveStringToFile(Text, *Path, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
	}

	bool ExportClip(UAnimSequence* Animation, const FString& Path, FScopedSlowTask& Progress, FString& Error)
	{
		const UAILocomotionDatasetSettings* Settings = GetDefault<UAILocomotionDatasetSettings>();
		USkeleton* Skeleton = Animation->GetSkeleton();
		if (!Skeleton || Animation->IsValidAdditive() || Settings->SampleRate < 1 || Settings->SampleRate > 120)
		{
			Error = LOCTEXT("InvalidAnimation", "动画必须有关联骨架、为非叠加动画，且采样率在 1–120 之间。").ToString();
			return false;
		}
		const double Duration = Animation->GetPlayLength();
		const double FrameCount = FMath::FloorToDouble(Duration * Settings->SampleRate) + 1;
		if (!FMath::IsFinite(Duration) || FrameCount < 2 || FrameCount > Settings->MaxFramesPerClip || FrameCount > 18000)
		{
			Error = LOCTEXT("InvalidDuration", "动画长度超出采样范围，请检查单片段最大帧数。").ToString();
			return false;
		}
		const FReferenceSkeleton& RefSkeleton = Skeleton->GetReferenceSkeleton();
		const int32 PelvisIndex = RefSkeleton.FindBoneIndex(Settings->PelvisBone);
		if (PelvisIndex == INDEX_NONE)
		{
			Error = FText::Format(LOCTEXT("MissingPelvis", "骨架缺少配置的骨盆 {0}，请在项目设置中指定正确骨骼。"), FText::FromName(Settings->PelvisBone)).ToString();
			return false;
		}
		TArray<FName> Names;
		TArray<int32> SourceIndices;
		TArray<int32> Parents;
		for (int32 Index = 0; Index < RefSkeleton.GetNum(); ++Index)
		{
			const int32 Parent = RefSkeleton.GetParentIndex(Index);
			if (Index == PelvisIndex || SourceIndices.Contains(Parent))
			{
				Parents.Add(Index == PelvisIndex ? INDEX_NONE : SourceIndices.IndexOfByKey(Parent));
				SourceIndices.Add(Index);
				Names.Add(RefSkeleton.GetBoneName(Index));
			}
		}
		const TArray<FName> Required = { Settings->LeftHipBone, Settings->RightHipBone, Settings->LeftFootBone, Settings->LeftToeBone, Settings->RightFootBone, Settings->RightToeBone };
		if (Names.IsEmpty() || Names.Num() > 512 || FrameCount * Names.Num() > 250000)
		{
			Error = LOCTEXT("InvalidSkeleton", "骨骼数超过 512，或帧数乘骨骼数超过 250000；请检查配置或拆分动画。").ToString();
			return false;
		}
		TSet<FName> RoleNames;
		for (FName Name : Required)
		{
			if (!Names.Contains(Name))
			{
				Error = FText::Format(LOCTEXT("MissingBone", "身体骨架缺少 {0}，请在项目设置中指定正确骨骼。"), FText::FromName(Name)).ToString();
				return false;
			}
			if (RoleNames.Contains(Name))
			{
				Error = FText::Format(LOCTEXT("DuplicateRole", "骨骼 {0} 被重复分配；左右髋和四个足部接触点必须使用不同骨骼。"), FText::FromName(Name)).ToString();
				return false;
			}
			RoleNames.Add(Name);
		}
		FAnimPose ReferencePose;
		UAnimPoseExtensions::GetReferencePose(Skeleton, ReferencePose);
		if (!ReferencePose.IsValid())
		{
			Error = LOCTEXT("InvalidReference", "无法读取骨架参考姿态。").ToString();
			return false;
		}
		TSharedRef<FJsonObject> Document = MakeShared<FJsonObject>();
		Document->SetNumberField(TEXT("schema_version"), 1);
		Document->SetStringField(TEXT("asset"), Animation->GetPathName());
		Document->SetStringField(TEXT("skeleton"), Skeleton->GetPathName());
		Document->SetStringField(TEXT("coordinate_system"), TEXT("unreal_component_cm_xyzw"));
		Document->SetNumberField(TEXT("fps"), Settings->SampleRate);
		Document->SetNumberField(TEXT("duration_seconds"), Duration);
		TArray<TSharedPtr<FJsonValue>> Bones;
		for (int32 Index = 0; Index < Names.Num(); ++Index)
		{
			const FTransform& Transform = UAnimPoseExtensions::GetRefBonePose(ReferencePose, Names[Index], EAnimPoseSpaces::World);
			if (Transform.ContainsNaN() || !Transform.GetScale3D().Equals(FVector::OneVector, 0.0001))
			{
				Error = LOCTEXT("InvalidReferenceTransform", "参考姿态包含非单位缩放或无效变换，请先规范化骨架。").ToString();
				return false;
			}
			const FVector Position = Transform.GetTranslation();
			const FQuat Rotation = Transform.GetRotation();
			TSharedRef<FJsonObject> Bone = MakeShared<FJsonObject>();
			Bone->SetStringField(TEXT("name"), Names[Index].ToString());
			Bone->SetNumberField(TEXT("parent"), Parents[Index]);
			Bone->SetArrayField(TEXT("position"), Numbers({ Position.X, Position.Y, Position.Z }));
			Bone->SetArrayField(TEXT("rotation"), Numbers({ Rotation.X, Rotation.Y, Rotation.Z, Rotation.W }));
			Bones.Add(MakeShared<FJsonValueObject>(Bone));
		}
		Document->SetArrayField(TEXT("bones"), Bones);
		TSharedRef<FJsonObject> Roles = MakeShared<FJsonObject>();
		Roles->SetStringField(TEXT("left_hip"), Settings->LeftHipBone.ToString());
		Roles->SetStringField(TEXT("right_hip"), Settings->RightHipBone.ToString());
		Roles->SetStringField(TEXT("left_foot"), Settings->LeftFootBone.ToString());
		Roles->SetStringField(TEXT("right_foot"), Settings->RightFootBone.ToString());
		Roles->SetStringField(TEXT("left_toe"), Settings->LeftToeBone.ToString());
		Roles->SetStringField(TEXT("right_toe"), Settings->RightToeBone.ToString());
		Document->SetObjectField(TEXT("roles"), Roles);

		// 使用原始求值且保留 root 运动，不依赖预览网格比例或压缩缓存。
		FAnimPoseEvaluationOptions Options;
		Options.EvaluationType = EAnimDataEvalType::Raw;
		Options.bShouldRetarget = false;
		Options.bExtractRootMotion = false;
		Options.bIncorporateRootMotionIntoPose = true;
		Options.bEvaluateCurves = false;
		TArray<TSharedPtr<FJsonValue>> Frames;
		for (int32 FrameIndex = 0; FrameIndex < static_cast<int32>(FrameCount); ++FrameIndex)
		{
			Progress.EnterProgressFrame(1.0f / static_cast<float>(FrameCount));
			if (Progress.ShouldCancel())
			{
				Error = LOCTEXT("Cancelled", "导出已取消；未发布训练清单。").ToString();
				return false;
			}
			FAnimPose Pose;
			UAnimPoseExtensions::GetAnimPoseAtTime(Animation, FrameIndex / static_cast<double>(Settings->SampleRate), Options, Pose);
			if (!Pose.IsValid())
			{
				Error = LOCTEXT("InvalidPose", "动画姿态求值失败。").ToString();
				return false;
			}
			TArray<FName> EvaluatedNames;
			UAnimPoseExtensions::GetBoneNames(Pose, EvaluatedNames);
			const TSet<FName> EvaluatedNameSet(EvaluatedNames);
			TArray<TSharedPtr<FJsonValue>> Transforms;
			for (FName Name : Names)
			{
				if (!EvaluatedNameSet.Contains(Name))
				{
					Error = FText::Format(LOCTEXT("MissingEvaluatedBone", "动画姿态缺少骨骼 {0}，无法导出完整身体姿态。"), FText::FromName(Name)).ToString();
					return false;
				}
				const FTransform& Transform = UAnimPoseExtensions::GetBonePose(Pose, Name, EAnimPoseSpaces::World);
				if (Transform.ContainsNaN() || !Transform.GetScale3D().Equals(FVector::OneVector, 0.0001))
				{
					Error = LOCTEXT("UnsupportedPose", "动画缺少骨骼、包含无效数值或缩放；当前训练表示要求刚性骨骼。").ToString();
					return false;
				}
				const FVector Position = Transform.GetTranslation();
				const FQuat Rotation = Transform.GetRotation();
				Transforms.Add(MakeShared<FJsonValueArray>(Numbers({ Position.X, Position.Y, Position.Z, Rotation.X, Rotation.Y, Rotation.Z, Rotation.W })));
			}
			Frames.Add(MakeShared<FJsonValueArray>(Transforms));
		}
		Document->SetArrayField(TEXT("frames"), Frames);
		if (!WriteJson(Path, Document))
		{
			Error = LOCTEXT("WriteFailed", "无法写入动画数据文件，请检查输出目录和磁盘空间。").ToString();
			return false;
		}
		return true;
	}

	void ExportSelected()
	{
		TArray<FAssetData> Assets;
		FModuleManager::LoadModuleChecked<FContentBrowserModule>(TEXT("ContentBrowser")).Get().GetSelectedAssets(Assets);
		if (Assets.IsEmpty())
		{
			FMessageDialog::Open(EAppMsgType::Ok, LOCTEXT("NoSelection", "请先在内容浏览器中选择 AnimSequence 动画资产。"));
			return;
		}
		const FString Directory = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / TEXT("AILocomotionDataset") / FGuid::NewGuid().ToString(EGuidFormats::Digits));
		IFileManager::Get().MakeDirectory(*Directory, true);
		FScopedSlowTask Progress(Assets.Num(), LOCTEXT("Exporting", "正在导出动画训练数据"));
		Progress.MakeDialog(true);
		TArray<TSharedPtr<FJsonValue>> Files;
		FString Error;
		for (int32 Index = 0; Index < Assets.Num(); ++Index)
		{
			UAnimSequence* Animation = Cast<UAnimSequence>(Assets[Index].GetAsset());
			const FString Filename = FString::Printf(TEXT("clip_%05d.json"), Index);
			if (!Animation || !ExportClip(Animation, Directory / Filename, Progress, Error))
			{
				if (!Animation)
				{
					Error = LOCTEXT("WrongAsset", "选中资产包含非 AnimSequence 类型。").ToString();
				}
				FMessageDialog::Open(EAppMsgType::Ok, FText::FromString(Assets[Index].GetObjectPathString() + TEXT("\n") + Error));
				return;
			}
			Files.Add(MakeShared<FJsonValueString>(Filename));
		}
		TSharedRef<FJsonObject> Manifest = MakeShared<FJsonObject>();
		Manifest->SetNumberField(TEXT("schema_version"), 1);
		Manifest->SetArrayField(TEXT("clips"), Files);
		if (!WriteJson(Directory / TEXT("manifest.json"), Manifest))
		{
			FMessageDialog::Open(EAppMsgType::Ok, LOCTEXT("ManifestFailed", "清单写入失败，批次未完成。"));
			return;
		}
		FMessageDialog::Open(EAppMsgType::Ok, FText::Format(LOCTEXT("Complete", "动画采样完成，输出目录：\n{0}\n下一步使用 prepare_unreal_dataset.py 生成训练特征。"), FText::FromString(Directory)));
	}
}

/** 菜单注册由模块生命周期持有，卸载时解除所有回调。 */
class FAILocomotionDatasetEditorModule : public IModuleInterface
{
public:
	virtual void StartupModule() override
	{
		UToolMenus::RegisterStartupCallback(FSimpleMulticastDelegate::FDelegate::CreateRaw(this, &FAILocomotionDatasetEditorModule::RegisterMenus));
	}

	virtual void ShutdownModule() override
	{
		UToolMenus::UnRegisterStartupCallback(this);
		UToolMenus::UnregisterOwner(this);
	}

private:
	void RegisterMenus()
	{
		FToolMenuOwnerScoped Owner(this);
		UToolMenu* Menu = UToolMenus::Get()->ExtendMenu(TEXT("LevelEditor.MainMenu.Tools"));
		FToolMenuSection& Section = Menu->FindOrAddSection(TEXT("AILocomotion"));
		Section.AddMenuEntry(TEXT("ExportAILocomotionDataset"), LOCTEXT("Export", "AI Locomotion：导出选中动画"),
			LOCTEXT("ExportTooltip", "读取内容浏览器选中的 AnimSequence，导出组件空间骨骼姿态与骨架信息。"), FSlateIcon(), FUIAction(FExecuteAction::CreateStatic(&ExportSelected)));
	}
};

IMPLEMENT_MODULE(FAILocomotionDatasetEditorModule, AILocomotionDatasetEditor)

#undef LOCTEXT_NAMESPACE
