// Copyright ZhaoZining. All Rights Reserved.

#include "AIAnimationWorkbench.h"
#include "AIAnimationModel.h"
#include "AIAnimationPreviewInstance.h"
#include "AIAnimationPreviewCache.h"
#include "AIAnimationReferenceSet.h"
#include "AdvancedPreviewScene.h"
#include "Algo/BinarySearch.h"
#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Brushes/SlateRoundedBoxBrush.h"
#include "CanvasItem.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/PoseableMeshComponent.h"
#include "EditorViewportClient.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "FileHelpers.h"
#include "Misc/Crc.h"
#include "HAL/IConsoleManager.h"
#include "HAL/FileManager.h"
#include "Modules/ModuleManager.h"
#include "Misc/PackageName.h"
#include "PropertyCustomizationHelpers.h"
#include "PrimitiveDrawInterface.h"
#include "ScopedTransaction.h"
#include "SEditorViewport.h"
#include "Styling/AppStyle.h"
#include "UObject/Package.h"
#include "UObject/StrongObjectPtr.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SCheckBox.h"
#include "Widgets/Input/SComboBox.h"
#include "Widgets/Input/SSearchBox.h"
#include "Widgets/Input/SSlider.h"
#include "Widgets/Input/SSpinBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SNullWidget.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

#define LOCTEXT_NAMESPACE "AIAnimationWorkbench"

namespace
{
	const FLinearColor Background(0.035f, 0.051f, 0.072f);
	const FLinearColor Panel(0.073f, 0.095f, 0.124f);
	const FLinearColor Mint(0.32f, 0.87f, 0.68f);
	const FLinearColor Orange(1.0f, 0.63f, 0.35f);
	const FLinearColor Blue(0.37f, 0.69f, 1.0f);
	const FSlateRoundedBoxBrush BackgroundBrush(Background, 10.0f);
	const FSlateRoundedBoxBrush PanelBrush(Panel, 10.0f);

	FString ReferencePackagePath(const UAnimSequence* Animation)
	{
		const uint32 PathHash = FCrc::StrCrc32(*Animation->GetPathName());
		return FString::Printf(TEXT("/Game/AIAnimationPreview/References/DA_%s_%08X"), *Animation->GetName(), PathHash);
	}

	class FAIAnimationViewportClient final : public FEditorViewportClient
	{
	public:
		FAIAnimationViewportClient(FAdvancedPreviewScene& Scene, const TSharedRef<SEditorViewport>& Viewport) : FEditorViewportClient(nullptr, &Scene, Viewport)
		{
			SetViewMode(VMI_Lit);
			SetViewportType(LVT_Perspective);
			SetViewLocation(FVector(390.0, 650.0, 210.0));
			SetViewRotation((FVector(0.0, 0.0, 100.0) - GetViewLocation()).Rotation());
			ViewFOV = 55.0f;
			SetRealtime(true);
			bUsingOrbitCamera = true;
			DrawHelper.bDrawGrid = true;
		}

		virtual void Tick(float DeltaSeconds) override
		{
			FEditorViewportClient::Tick(DeltaSeconds);
			if (!bManualAnimationTick && !bAnimationPaused)
			{
				const float StepSeconds = 1.0f / LiveFramesPerSecond;
				LiveAccumulator += FMath::Clamp(DeltaSeconds, 0.0f, 0.25f);
				const int32 Steps = FMath::Min(8, FMath::FloorToInt(LiveAccumulator / StepSeconds));
				LiveAccumulator -= Steps * StepSeconds;
				for (int32 Step = 0; Step < Steps; ++Step)
				{
					PreviewScene->GetWorld()->Tick(LEVELTICK_All, StepSeconds);
				}
			}
		}

		void SetManualAnimationTick(bool bManual) { bManualAnimationTick = bManual; LiveAccumulator = 0.0f; }
		void SetAnimationPaused(bool bPaused) { bAnimationPaused = bPaused; LiveAccumulator = 0.0f; }
		void SetLiveFramesPerSecond(int32 FramesPerSecond) { LiveFramesPerSecond = FMath::Clamp(FramesPerSecond, 1, 240); LiveAccumulator = 0.0f; }
		void AdvanceAnimationWorld(float DeltaSeconds) { PreviewScene->GetWorld()->Tick(LEVELTICK_All, DeltaSeconds); }

		void SetOverlays(USkinnedMeshComponent* InLabelMesh, const TArray<FVector>* InRootTrack, int32 InCurrentRootSample, bool bInShowTrajectory)
		{
			LabelMesh = InLabelMesh;
			RootTrack = InRootTrack;
			CurrentRootSample = InCurrentRootSample;
			bShowTrajectory = bInShowTrajectory;
		}

		void SetBoneLabelOptions(const FString& InFilter, bool bInShowAll)
		{
			BoneFilter = InFilter;
			bShowAllBoneLabels = bInShowAll;
		}

		virtual void Draw(const FSceneView* View, FPrimitiveDrawInterface* PDI) override
		{
			FEditorViewportClient::Draw(View, PDI);
			if (!bShowTrajectory || !RootTrack || RootTrack->IsEmpty())
			{
				return;
			}

			const FVector GroundOffset(0.0, 0.0, 3.0);
			for (int32 Index = 1; Index < RootTrack->Num(); ++Index)
			{
				const FLinearColor Color = Index <= CurrentRootSample ? Mint : FLinearColor(0.25f, 0.38f, 0.42f);
				PDI->DrawLine((*RootTrack)[Index - 1] + GroundOffset, (*RootTrack)[Index] + GroundOffset, Color, SDPG_Foreground, 2.0f);
			}
			PDI->DrawPoint((*RootTrack)[0] + GroundOffset, Blue, 11.0f, SDPG_Foreground);
			PDI->DrawPoint(RootTrack->Last() + GroundOffset, Orange, 11.0f, SDPG_Foreground);
			const FVector Current = (*RootTrack)[FMath::Clamp(CurrentRootSample, 0, RootTrack->Num() - 1)] + GroundOffset;
			PDI->DrawPoint(Current, Mint, 17.0f, SDPG_Foreground);
			PDI->DrawLine(Current, Current + FVector(0.0, 0.0, 45.0), Mint, SDPG_Foreground, 1.5f);
		}

		virtual void DrawCanvas(FViewport& InViewport, FSceneView& View, FCanvas& Canvas) override
		{
			FEditorViewportClient::DrawCanvas(InViewport, View, Canvas);
			if (!LabelMesh.IsValid() || !LabelMesh->GetSkinnedAsset())
			{
				return;
			}
			int32 DrawnCount = 0;
			TArray<FIntRect> OccupiedLabels;
			for (int32 BoneIndex = 0; BoneIndex < LabelMesh->GetNumBones(); ++BoneIndex)
			{
				const FString BoneName = LabelMesh->GetBoneName(BoneIndex).ToString();
				if (!BoneFilter.IsEmpty() && !BoneName.Contains(BoneFilter, ESearchCase::IgnoreCase))
				{
					continue;
				}
				FVector2D Pixel;
				if (!View.WorldToPixel(LabelMesh->GetBoneTransform(BoneIndex).GetLocation(), Pixel) || Pixel.X < 0.0f || Pixel.Y < 0.0f || Pixel.X >= InViewport.GetSizeXY().X || Pixel.Y >= InViewport.GetSizeXY().Y)
				{
					continue;
				}
				const FVector2D CanvasPixel = Pixel / GetDPIScale();
				int32 TextHeight = 0;
				int32 TextWidth = 0;
				GEngine->GetSmallFont()->GetStringHeightAndWidth(BoneName, TextHeight, TextWidth);
				const FIntPoint TopLeft(FMath::FloorToInt(CanvasPixel.X + 5.0f), FMath::FloorToInt(CanvasPixel.Y - 11.0f));
				const FIntRect LabelRect(TopLeft, TopLeft + FIntPoint(TextWidth + 5, TextHeight + 3));
				if (!bShowAllBoneLabels && OccupiedLabels.ContainsByPredicate([&LabelRect](const FIntRect& Existing) { return Existing.Intersect(LabelRect); }))
				{
					continue;
				}
				OccupiedLabels.Add(LabelRect);
				FCanvasTileItem Joint(CanvasPixel - FVector2D(2.0f, 2.0f), FVector2D(4.0f, 4.0f), Mint);
				Canvas.DrawItem(Joint);
				FCanvasTextItem Name(CanvasPixel + FVector2D(5.0f, -11.0f), FText::FromString(BoneName), GEngine->GetSmallFont(), FLinearColor::White);
				Name.EnableShadow(FLinearColor::Black);
				Canvas.DrawItem(Name);
				++DrawnCount;
			}
			FCanvasTextItem LabelCount(FVector2D(16.0f, 16.0f), FText::FromString(FString::Printf(TEXT("可见骨骼名 %d/%d  ·  缩放或搜索查看"), DrawnCount, LabelMesh->GetNumBones())), GEngine->GetSmallFont(), Mint);
			LabelCount.EnableShadow(FLinearColor::Black);
			Canvas.DrawItem(LabelCount);
		}

	private:
		TWeakObjectPtr<USkinnedMeshComponent> LabelMesh;
		const TArray<FVector>* RootTrack = nullptr;
		int32 CurrentRootSample = 0;
		bool bShowTrajectory = true;
		bool bShowAllBoneLabels = false;
		FString BoneFilter;
		bool bManualAnimationTick = false;
		bool bAnimationPaused = false;
		int32 LiveFramesPerSecond = 30;
		float LiveAccumulator = 0.0f;
	};

	class SAIAnimationPreviewViewport final : public SEditorViewport
	{
	public:
		SLATE_BEGIN_ARGS(SAIAnimationPreviewViewport) {}
		SLATE_END_ARGS()

		void Construct(const FArguments& Args)
		{
			Scene = MakeUnique<FAdvancedPreviewScene>(FPreviewScene::ConstructionValues());
			for (int32 Index = 0; Index < 3; ++Index)
			{
				Meshes[Index].Reset(NewObject<USkeletalMeshComponent>(GetTransientPackage()));
				Meshes[Index]->bEnableUpdateRateOptimizations = false;
				Meshes[Index]->SetForcedLOD(1);
				Meshes[Index]->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
				Meshes[Index]->SetDisablePostProcessBlueprint(true);
				Meshes[Index]->bSuppressNotifyEventDispatch = true;
				Scene->AddComponent(Meshes[Index].Get(), FTransform(FVector((Index - 1) * 190.0, 0.0, 0.0)));
				CachedMeshes[Index].Reset(NewObject<UPoseableMeshComponent>(GetTransientPackage()));
				CachedMeshes[Index]->SetForcedLOD(1);
				Scene->AddComponent(CachedMeshes[Index].Get(), FTransform(FVector((Index - 1) * 190.0, 0.0, 0.0)));
				CachedMeshes[Index]->SetVisibility(false);
			}
			SEditorViewport::Construct(SEditorViewport::FArguments());
		}

		virtual FVector2D ComputeDesiredSize(float) const override
		{
			return FVector2D(640.0f, 360.0f);
		}

		void SetAssets(UAnimSequence* Animation, UAIAnimationModel* Model, TConstArrayView<int32> Frames)
		{
			PreviewAnimation = Animation;
			PreviewModel = Model;
			RootTrack.Reset();
			RootTrackLength = 0.0;
			if (Animation)
			{
				const int32 LastSample = FMath::Max(1, FMath::CeilToInt(Animation->GetPlayLength() * 30.0f));
				RootTrack.Reserve(LastSample + 1);
				for (int32 Sample = 0; Sample <= LastSample; ++Sample)
				{
					const double Seconds = Animation->GetPlayLength() * Sample / LastSample;
					const FVector Position = Animation->ExtractRootMotionFromRange(0.0, Seconds, FAnimExtractContext(Seconds, true)).GetTranslation();
					if (!RootTrack.IsEmpty())
					{
						RootTrackLength += FVector::Distance(RootTrack.Last(), Position);
					}
					RootTrack.Add(Position);
				}
			}
			USkeletalMesh* Mesh = Animation && Animation->GetSkeleton() ? Animation->GetSkeleton()->GetPreviewMesh(true) : nullptr;
			for (int32 Index = 0; Index < 3; ++Index)
			{
				Meshes[Index]->SetSkeletalMesh(Mesh);
				Meshes[Index]->SetForcedLOD(1);
				CachedMeshes[Index]->SetSkinnedAssetAndUpdate(Mesh);
				CachedMeshes[Index]->SetForcedLOD(1);
				if (!Mesh || !Animation)
				{
					continue;
				}
				Meshes[Index]->SetAnimInstanceClass(UAIAnimationPreviewInstance::StaticClass());
				UAIAnimationPreviewInstance* Instance = Cast<UAIAnimationPreviewInstance>(Meshes[Index]->GetAnimInstance());
				if (!Instance)
				{
					continue;
				}
				Instance->Sequence = Animation;
				Instance->ReconstructionModel = Model;
				Instance->bReferenceOnly = Index == 0;
				Instance->bReconstruct = Index != 0;
				Instance->HardReferenceFrames = Index == 2 ? TArray<int32>(Frames) : TArray<int32>();
				Instance->bPaused = bPaused;
				Instance->PlaybackRate = PlaybackRate;
				Instance->InitializeAnimation();
			}
			Invalidate();
			ApplyRootMotion();
		}

		void SetReplayCache(const FAIAnimationPreviewCache* InCache)
		{
			const int32 ExpectedBones = Meshes[0]->GetNumBones();
			const bool bValid = InCache && ExpectedBones > 0 && !InCache->Frames.IsEmpty()
				&& !InCache->Frames.ContainsByPredicate([ExpectedBones](const FAIAnimationCachedFrame& Frame)
				{
					return Frame.BoneComponent[0].Num() != ExpectedBones || Frame.BoneComponent[1].Num() != ExpectedBones
						|| Frame.BoneComponent[2].Num() != ExpectedBones;
				});
			ReplayCache = bValid ? InCache : nullptr;
			bReplayMode = ReplayCache && !ReplayCache->Frames.IsEmpty();
			ReplayAccumulator = 0.0f;
			for (int32 Index = 0; Index < 3; ++Index)
			{
				Meshes[Index]->SetVisibility(!bReplayMode);
				Meshes[Index]->SetComponentTickEnabled(!bReplayMode);
				CachedMeshes[Index]->SetVisibility(bReplayMode);
			}
			if (bReplayMode)
			{
				SetPaused(true);
				ApplyReplayIndex(0);
			}
			UpdateOverlays();
		}

		void BeginCacheBuild(float StartSeconds)
		{
			SetReplayCache(nullptr);
			for (int32 Index = 0; Index < 3; ++Index)
			{
				if (UAIAnimationPreviewInstance* Instance = GetInstance(Index))
				{
					Instance->bLoopAnimation = false;
				}
			}
			if (ViewportClient.IsValid())
			{
				ViewportClient->SetManualAnimationTick(true);
			}
			Seek(StartSeconds, true);
			SetPaused(true);
		}

		FAIAnimationCachedFrame CaptureCacheFrame(int32 OutputIndex, int32 FramesPerSecond, float StartSeconds, float Speed)
		{
			const float TargetTime = StartSeconds + OutputIndex * Speed / FMath::Max(1, FramesPerSecond);
			if (OutputIndex > 0)
			{
				SetPaused(false);
				ViewportClient->AdvanceAnimationWorld(1.0f / FMath::Max(1, FramesPerSecond));
				SetPaused(true);
			}
			// World Tick 可能只发起并行动画求值；读取三路姿态前先完成全部骨骼刷新。
			for (TStrongObjectPtr<USkeletalMeshComponent>& Mesh : Meshes)
			{
				Mesh->RefreshBoneTransforms();
			}
			FAIAnimationCachedFrame Frame;
			Frame.SourceTimeSeconds = TargetTime;
			for (int32 Index = 0; Index < 3; ++Index)
			{
				Frame.BoneComponent[Index] = Meshes[Index]->GetComponentSpaceTransforms();
			}
			if (PreviewModel.IsValid() && Meshes[0]->GetSkeletalMeshAsset())
			{
				const FReferenceSkeleton& Skeleton = Meshes[0]->GetSkeletalMeshAsset()->GetRefSkeleton();
				const TArray<FTransform>& Source = Frame.BoneComponent[0];
				if (Source.Num() == Skeleton.GetNum())
				{
					for (int32 MeshIndex = 1; MeshIndex < 3; ++MeshIndex)
					{
						const TArray<FTransform> ModelPose = MoveTemp(Frame.BoneComponent[MeshIndex]);
						if (ModelPose.Num() != Source.Num())
						{
							Frame.BoneComponent[MeshIndex] = Source;
							continue;
						}
						TArray<FTransform> Local;
						Local.SetNumUninitialized(Source.Num());
						Local[0] = Source[0];
						for (int32 BoneIndex = 1; BoneIndex < Source.Num(); ++BoneIndex)
						{
							Local[BoneIndex] = Source[BoneIndex].GetRelativeTransform(Source[Skeleton.GetParentIndex(BoneIndex)]);
						}
						for (const FAIAnimationBone& Bone : PreviewModel->Bones)
						{
							const int32 BoneIndex = Meshes[MeshIndex]->GetBoneIndex(Bone.Name);
							if (BoneIndex > 0 && BoneIndex < Local.Num())
							{
								Local[BoneIndex] = ModelPose[BoneIndex].GetRelativeTransform(ModelPose[Skeleton.GetParentIndex(BoneIndex)]);
							}
						}
						TArray<FTransform>& Aligned = Frame.BoneComponent[MeshIndex];
						Aligned.SetNumUninitialized(Local.Num());
						Aligned[0] = Local[0];
						for (int32 BoneIndex = 1; BoneIndex < Local.Num(); ++BoneIndex)
						{
							Aligned[BoneIndex] = Local[BoneIndex] * Aligned[Skeleton.GetParentIndex(BoneIndex)];
						}
					}
				}
			}
			if (OutputIndex % 10 == 0 || (GetInstance(2) && GetInstance(2)->HardReferenceFrames.Contains(FMath::RoundToInt(TargetTime * 30.0f))))
			{
				auto PoseDistance = [&Frame](int32 First, int32 Second)
				{
					float Distance = 0.0f;
					const int32 Count = FMath::Min(Frame.BoneComponent[First].Num(), Frame.BoneComponent[Second].Num());
					for (int32 Bone = 0; Bone < Count; ++Bone)
					{
						Distance += FVector::Dist(Frame.BoneComponent[First][Bone].GetTranslation(), Frame.BoneComponent[Second][Bone].GetTranslation());
					}
					return Count > 0 ? Distance / Count : 0.0f;
				};
				UE_LOG(LogTemp, Display, TEXT("AIAnimationCacheCapture output=%d target=%.3f actual=%.3f laneTimes=%.3f/%.3f/%.3f boneCounts=%d/%d/%d softSource=%.3f hardSource=%.3f softHard=%.3f references=%d inferences=%llu"),
					OutputIndex, Frame.SourceTimeSeconds, GetSourceTime(), GetInstance(0) ? GetInstance(0)->CurrentAssetTimeSeconds : -1.0f,
					GetInstance(1) ? GetInstance(1)->CurrentAssetTimeSeconds : -1.0f, GetInstance(2) ? GetInstance(2)->CurrentAssetTimeSeconds : -1.0f,
					Frame.BoneComponent[0].Num(), Frame.BoneComponent[1].Num(), Frame.BoneComponent[2].Num(),
					PoseDistance(0, 1), PoseDistance(0, 2), PoseDistance(1, 2), GetInstance(2) ? GetInstance(2)->HardReferenceFrames.Num() : 0,
					GetHardStats() ? GetHardStats()->NumInferences : 0);
			}
			if (const FAIAnimationEvaluationStats* Stats = GetHardStats())
			{
				Frame.InferenceMs = Stats->LastInferenceMs;
				Frame.JointErrorCm = Stats->LastJointErrorCm;
				Frame.NumInferences = Stats->NumInferences;
				Frame.NumQualitySamples = Stats->NumQualitySamples;
			}
			ApplyRootMotion();
			Invalidate();
			return Frame;
		}

		void FinishCacheBuild(const FAIAnimationPreviewCache* InCache)
		{
			for (int32 Index = 0; Index < 3; ++Index)
			{
				if (UAIAnimationPreviewInstance* Instance = GetInstance(Index))
				{
					Instance->bLoopAnimation = true;
				}
			}
			if (ViewportClient.IsValid())
			{
				ViewportClient->SetManualAnimationTick(false);
			}
			SetReplayCache(InCache);
		}

		bool IsReplayMode() const { return bReplayMode; }
		int32 GetPreviewBoneCount() const { return Meshes[0]->GetNumBones(); }
		void LogLiveAlignment(int32 SourceFrame)
		{
			for (TStrongObjectPtr<USkeletalMeshComponent>& Mesh : Meshes)
			{
				Mesh->RefreshBoneTransforms();
			}
			const TArray<FTransform>& Source = Meshes[0]->GetComponentSpaceTransforms();
			const TArray<FTransform>& Soft = Meshes[1]->GetComponentSpaceTransforms();
			const TArray<FTransform>& Hard = Meshes[2]->GetComponentSpaceTransforms();
			if (Source.IsEmpty() || Source.Num() != Soft.Num() || Source.Num() != Hard.Num())
			{
				UE_LOG(LogTemp, Warning, TEXT("AIAnimationLiveCheck frame=%d invalid bone counts=%d/%d/%d"), SourceFrame, Source.Num(), Soft.Num(), Hard.Num());
				return;
			}
			double SoftError = 0.0;
			double HardError = 0.0;
			for (int32 Bone = 0; Bone < Source.Num(); ++Bone)
			{
				SoftError += FVector::Distance(Source[Bone].GetTranslation(), Soft[Bone].GetTranslation());
				HardError += FVector::Distance(Source[Bone].GetTranslation(), Hard[Bone].GetTranslation());
			}
			UE_LOG(LogTemp, Display, TEXT("AIAnimationLiveCheck frame=%d laneTimes=%.6f/%.6f/%.6f softSource=%.3f hardSource=%.3f bones=%d"),
				SourceFrame, GetInstance(0)->CurrentAssetTimeSeconds, GetInstance(1)->CurrentAssetTimeSeconds,
				GetInstance(2)->CurrentAssetTimeSeconds, SoftError / Source.Num(), HardError / Source.Num(), Source.Num());
		}

		void TickReplay(float DeltaSeconds, int32 FramesPerSecond)
		{
			if (!bReplayMode || bPaused || !ReplayCache || ReplayCache->Frames.IsEmpty())
			{
				return;
			}
			ReplayAccumulator += FMath::Clamp(DeltaSeconds, 0.0f, 0.25f);
			const int32 StepCount = FMath::FloorToInt(ReplayAccumulator * FramesPerSecond);
			if (StepCount > 0)
			{
				ReplayAccumulator -= StepCount / static_cast<float>(FramesPerSecond);
				ApplyReplayIndex((ReplayIndex + StepCount) % ReplayCache->Frames.Num());
			}
		}

		void SetBoneNamesVisible(bool bVisible)
		{
			bShowBoneNames = bVisible;
			UpdateOverlays();
		}

		void SetTrajectoryVisible(bool bVisible)
		{
			bShowTrajectory = bVisible;
			UpdateOverlays();
		}

		void SetBoneLabelTarget(int32 Index)
		{
			BoneLabelTarget = FMath::Clamp(Index, 0, 2);
			UpdateOverlays();
		}

		void SetBoneLabelOptions(const FString& Filter, bool bShowAll)
		{
			BoneFilter = Filter;
			bShowAllBoneLabels = bShowAll;
			UpdateOverlays();
		}

		void SetReferenceFrames(TConstArrayView<int32> Frames)
		{
			if (UAIAnimationPreviewInstance* Instance = GetInstance(2))
			{
				Instance->HardReferenceFrames = TArray<int32>(Frames);
			}
		}

		void SetPaused(bool bInPaused)
		{
			bPaused = bInPaused;
			if (ViewportClient.IsValid())
			{
				ViewportClient->SetAnimationPaused(bPaused);
			}
			for (int32 Index = 0; Index < 3; ++Index)
			{
				if (UAIAnimationPreviewInstance* Instance = GetInstance(Index))
				{
					Instance->bPaused = bPaused;
				}
			}
		}

		void SetPlaybackRate(float InRate)
		{
			PlaybackRate = FMath::Clamp(InRate, 0.00001f, 1000.0f);
			for (int32 Index = 0; Index < 3; ++Index)
			{
				if (UAIAnimationPreviewInstance* Instance = GetInstance(Index))
				{
					Instance->PlaybackRate = PlaybackRate;
				}
			}
		}

		void SetLiveFramesPerSecond(int32 FramesPerSecond)
		{
			if (ViewportClient.IsValid())
			{
				ViewportClient->SetLiveFramesPerSecond(FramesPerSecond);
			}
		}

		void SetRootMotion(bool bEnabled)
		{
			bShowRootMotion = bEnabled;
			ApplyRootMotion();
		}

		void ApplyRootMotion()
		{
			const FTransform Motion = bShowRootMotion && PreviewAnimation.IsValid() ? PreviewAnimation->ExtractRootMotionFromRange(0.0, GetCurrentTime(), FAnimExtractContext(GetCurrentTime(), true)) : FTransform::Identity;
			for (int32 Index = 0; Index < 3; ++Index)
			{
				const FVector Location = FVector((Index - 1) * 190.0, 0.0, 0.0) + Motion.GetTranslation();
				Meshes[Index]->SetWorldLocation(Location);
				Meshes[Index]->SetWorldRotation(Motion.GetRotation());
				CachedMeshes[Index]->SetWorldLocation(Location);
				CachedMeshes[Index]->SetWorldRotation(Motion.GetRotation());
			}
			UpdateOverlays();
		}

		FText GetRootMetricsText() const
		{
			if (!PreviewAnimation.IsValid() || RootTrack.IsEmpty())
			{
				return LOCTEXT("RootMetricsEmpty", "选择动画后显示 Root 轨迹数据");
			}
			const double Seconds = FMath::Clamp(static_cast<double>(GetCurrentTime()), 0.0, PreviewAnimation->GetPlayLength());
			const FTransform Motion = PreviewAnimation->ExtractRootMotionFromRange(0.0, Seconds, FAnimExtractContext(Seconds, true));
			const FVector Position = Motion.GetTranslation();
			const double PreviousSeconds = FMath::Max(0.0, Seconds - 1.0 / 30.0);
			const FVector PreviousPosition = PreviewAnimation->ExtractRootMotionFromRange(0.0, PreviousSeconds, FAnimExtractContext(PreviousSeconds, true)).GetTranslation();
			const double Speed = Seconds > PreviousSeconds ? FVector::Distance(Position, PreviousPosition) / (Seconds - PreviousSeconds) : 0.0;
			return FText::FromString(FString::Printf(TEXT("Root 位移  X %.1f  Y %.1f  Z %.1f cm\n水平位移  %.1f cm   速度  %.1f cm/s\n轨迹总长  %.1f cm   朝向  %.1f°"),
				Position.X, Position.Y, Position.Z, FVector2D(Position.X, Position.Y).Size(), Speed, RootTrackLength, Motion.Rotator().Yaw));
		}

		void PreviewScrub(float Seconds)
		{
			if (bReplayMode)
			{
				SeekReplay(Seconds);
				return;
			}
			if (!PreviewAnimation.IsValid() || !GetInstance(0))
			{
				return;
			}
			Seek(Seconds, true);
			if (ViewportClient.IsValid())
			{
				ViewportClient->Invalidate(false, false);
			}
			Invalidate();
		}

		void Seek(float Seconds, bool bForceWarmup = false)
		{
			if (bReplayMode)
			{
				SeekReplay(Seconds);
				SetPaused(true);
				return;
			}
			if (!PreviewAnimation.IsValid() || !GetInstance(0))
			{
				return;
			}
			const FAIAnimationEvaluationStats* Stats = GetHardStats();
			const float SourceSeconds = FMath::Clamp(Seconds + (Stats ? Stats->DelayFrames / 30.0f : 0.0f), 0.0f, FMath::Max(0.0f, PreviewAnimation->GetPlayLength() - 0.001f));
			const float CurrentSourceSeconds = GetSourceTime();
			const bool bCanContinue = !bForceWarmup && SourceSeconds >= CurrentSourceSeconds && SourceSeconds - CurrentSourceSeconds <= 0.25f;
			const float WarmupStartSeconds = bCanContinue ? CurrentSourceSeconds : FMath::Max(0.0f, SourceSeconds - 1.5f);
			const float RestoredPlaybackRate = PlaybackRate;
			bPaused = false;
			for (int32 Index = 0; Index < 3; ++Index)
			{
				if (UAIAnimationPreviewInstance* Instance = GetInstance(Index))
				{
					Instance->bPaused = false;
					Instance->PlaybackRate = 1.0f;
					if (!bCanContinue)
					{
						Instance->RequestedAssetTimeSeconds = WarmupStartSeconds;
					}
				}
			}
			if (!bCanContinue)
			{
				AdvancePreview(0.0f);
			}
			for (int32 Step = 0; Step < 96 && GetSourceTime() < SourceSeconds - 0.005f; ++Step)
			{
				const float Remaining = SourceSeconds - GetSourceTime();
				AdvancePreview(FMath::Clamp(Remaining, 0.001f, 1.0f / 30.0f));
			}
			SetPaused(true);
			SetPlaybackRate(RestoredPlaybackRate);
			ApplyRootMotion();
			Invalidate();
		}

		float GetCurrentTime() const
		{
			if (bReplayMode && ReplayCache && ReplayCache->Frames.IsValidIndex(ReplayIndex))
			{
				return ReplayCache->Frames[ReplayIndex].SourceTimeSeconds;
			}
			const UAIAnimationPreviewInstance* Instance = GetInstance(1) ? GetInstance(1) : GetInstance(0);
			const FAIAnimationEvaluationStats* Stats = GetHardStats();
			return Instance ? FMath::Max(0.0f, Instance->CurrentAssetTimeSeconds - (Stats ? Stats->DelayFrames / 30.0f : 0.0f)) : 0.0f;
		}

		float GetSourceTime() const
		{
			const UAIAnimationPreviewInstance* Instance = GetInstance(1) ? GetInstance(1) : GetInstance(0);
			return Instance ? Instance->CurrentAssetTimeSeconds : 0.0f;
		}

		float GetDisplayDelay() const
		{
			const FAIAnimationEvaluationStats* Stats = GetHardStats();
			return Stats ? Stats->DelayFrames / 30.0f : 0.0f;
		}

		const FAIAnimationEvaluationStats* GetHardStats() const
		{
			if (bReplayMode)
			{
				return &ReplayStats;
			}
			const UAIAnimationPreviewInstance* Instance = GetInstance(2);
			return Instance ? &Instance->EvaluationStats : nullptr;
		}

	protected:
		virtual TSharedRef<FEditorViewportClient> MakeEditorViewportClient() override
		{
			ViewportClient = MakeShared<FAIAnimationViewportClient>(*Scene, StaticCastSharedRef<SEditorViewport>(SharedThis(this)));
			UpdateOverlays();
			return ViewportClient.ToSharedRef();
		}

		virtual TSharedPtr<SWidget> BuildViewportToolbar() override { return SNullWidget::NullWidget; }

	private:
		void SeekReplay(float Seconds)
		{
			if (!bReplayMode || !ReplayCache || ReplayCache->Frames.IsEmpty())
			{
				return;
			}
			const TArray<FAIAnimationCachedFrame>& Frames = ReplayCache->Frames;
			int32 Upper = Algo::LowerBoundBy(Frames, Seconds, &FAIAnimationCachedFrame::SourceTimeSeconds);
			Upper = FMath::Clamp(Upper, 0, Frames.Num() - 1);
			const int32 Lower = FMath::Max(0, Upper - 1);
			const int32 Target = FMath::Abs(Frames[Lower].SourceTimeSeconds - Seconds) <= FMath::Abs(Frames[Upper].SourceTimeSeconds - Seconds) ? Lower : Upper;
			ApplyReplayIndex(Target);
		}

		void ApplyReplayIndex(int32 Index)
		{
			if (!ReplayCache || !ReplayCache->Frames.IsValidIndex(Index))
			{
				return;
			}
			ReplayIndex = Index;
			const FAIAnimationCachedFrame& Frame = ReplayCache->Frames[Index];
			for (int32 MeshIndex = 0; MeshIndex < 3; ++MeshIndex)
			{
				UPoseableMeshComponent* Target = CachedMeshes[MeshIndex].Get();
				if (!Target || Frame.BoneComponent[MeshIndex].Num() != Target->GetNumBones())
				{
					continue;
				}
				for (int32 BoneIndex = 0; BoneIndex < Target->GetNumBones(); ++BoneIndex)
				{
					Target->SetBoneTransformByName(Target->GetBoneName(BoneIndex), Frame.BoneComponent[MeshIndex][BoneIndex], EBoneSpaces::ComponentSpace);
				}
				Target->RefreshBoneTransforms();
			}
			ReplayStats.LastInferenceMs = Frame.InferenceMs;
			ReplayStats.LastJointErrorCm = Frame.JointErrorCm;
			ReplayStats.NumInferences = Frame.NumInferences;
			ReplayStats.NumQualitySamples = Frame.NumQualitySamples;
			ApplyRootMotion();
			if (ViewportClient.IsValid())
			{
				ViewportClient->Invalidate(false, false);
			}
			Invalidate();
		}

		void AdvancePreview(float DeltaSeconds)
		{
			for (TStrongObjectPtr<USkeletalMeshComponent>& Mesh : Meshes)
			{
				Mesh->TickAnimation(DeltaSeconds, false);
				Mesh->RefreshBoneTransforms();
			}
		}

		void UpdateOverlays()
		{
			if (ViewportClient.IsValid())
			{
				const int32 CurrentSample = RootTrack.Num() > 1 && PreviewAnimation.IsValid() && PreviewAnimation->GetPlayLength() > 0.0f
					? FMath::Clamp(FMath::RoundToInt(GetCurrentTime() / PreviewAnimation->GetPlayLength() * (RootTrack.Num() - 1)), 0, RootTrack.Num() - 1) : 0;
			ViewportClient->SetOverlays(bShowBoneNames ? (bReplayMode ? static_cast<USkinnedMeshComponent*>(CachedMeshes[BoneLabelTarget].Get()) : static_cast<USkinnedMeshComponent*>(Meshes[BoneLabelTarget].Get())) : nullptr, &RootTrack, CurrentSample, bShowTrajectory);
				ViewportClient->SetBoneLabelOptions(BoneFilter, bShowAllBoneLabels);
				Invalidate();
			}
		}

		UAIAnimationPreviewInstance* GetInstance(int32 Index) const
		{
			return Meshes[Index].IsValid() ? Cast<UAIAnimationPreviewInstance>(Meshes[Index]->GetAnimInstance()) : nullptr;
		}

		TUniquePtr<FAdvancedPreviewScene> Scene;
		TSharedPtr<FAIAnimationViewportClient> ViewportClient;
		TStrongObjectPtr<USkeletalMeshComponent> Meshes[3];
		TStrongObjectPtr<UPoseableMeshComponent> CachedMeshes[3];
		const FAIAnimationPreviewCache* ReplayCache = nullptr;
		FAIAnimationEvaluationStats ReplayStats;
		int32 ReplayIndex = 0;
		float ReplayAccumulator = 0.0f;
		bool bReplayMode = false;
		TWeakObjectPtr<UAnimSequence> PreviewAnimation;
		TWeakObjectPtr<UAIAnimationModel> PreviewModel;
		TArray<FVector> RootTrack;
		double RootTrackLength = 0.0;
		bool bPaused = false;
		float PlaybackRate = 1.0f;
		bool bShowRootMotion = false;
		bool bShowBoneNames = true;
		bool bShowTrajectory = true;
		int32 BoneLabelTarget = 2;
		bool bShowAllBoneLabels = false;
		FString BoneFilter;
	};

	class SAIAnimationWorkbench final : public SCompoundWidget
	{
	public:
		SLATE_BEGIN_ARGS(SAIAnimationWorkbench) {}
		SLATE_END_ARGS()

		void Construct(const FArguments& Args)
		{
			if (IConsoleVariable* MaxFpsVariable = IConsoleManager::Get().FindConsoleVariable(TEXT("t.MaxFPS")))
			{
				PreviousMaxFps = MaxFpsVariable->GetFloat();
				MaxFpsVariable->Set(OutputFps, ECVF_SetByConsole);
			}
			for (const float Rate : { 0.25f, 0.5f, 0.75f, 1.0f, 1.25f, 1.5f, 1.75f, 2.0f })
			{
				SpeedPresets.Add(MakeShared<float>(Rate));
			}
			ChildSlot
			[
				SNew(SBorder).BorderImage(&BackgroundBrush).Padding(12)
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 10)
					[
						SNew(SBorder).BorderImage(&PanelBrush).Padding(FMargin(14, 10))
						[
							SNew(SHorizontalBox)
							+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0, 0, 22, 0)[SNew(STextBlock).Text(LOCTEXT("Title", "AIAnimation 预览工作台")).Font(FAppStyle::GetFontStyle("HeadingExtraSmall"))]
							+ SHorizontalBox::Slot().FillWidth(1)[SNew(SObjectPropertyEntryBox).AllowedClass(UAnimSequence::StaticClass()).ObjectPath_Lambda([this] { return Animation.IsValid() ? Animation->GetPathName() : FString(); }).OnObjectChanged_Lambda([this](const FAssetData& Asset) { SelectAnimation(Cast<UAnimSequence>(Asset.GetAsset())); })]
							+ SHorizontalBox::Slot().AutoWidth().Padding(12, 0)[SNew(STextBlock).Text_Lambda([this] { return bDirty ? LOCTEXT("Unsaved", "● 未保存") : LOCTEXT("Saved", "已保存"); }).ColorAndOpacity(Mint)]
							+ SHorizontalBox::Slot().AutoWidth()[SNew(SButton).Text(LOCTEXT("Save", "保存参考")).OnClicked(this, &SAIAnimationWorkbench::SaveReferences)]
						]
					]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 8)
					[
						SNew(SBorder).BorderImage(&PanelBrush).Padding(FMargin(12, 6))
						[
							SNew(SHorizontalBox)
							+ SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 14, 0)[SNew(SCheckBox).Style(FAppStyle::Get(), "RadioButton").IsChecked_Lambda([this] { return !bReplayRequested ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }).OnCheckStateChanged_Lambda([this](ECheckBoxState State) { if (State == ECheckBoxState::Checked) { SwitchPreviewMode(false); } })[SNew(STextBlock).Text(LOCTEXT("LiveMode", "实时预览"))]]
							+ SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 14, 0)[SNew(SCheckBox).Style(FAppStyle::Get(), "RadioButton").IsChecked_Lambda([this] { return bReplayRequested ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }).OnCheckStateChanged_Lambda([this](ECheckBoxState State) { if (State == ECheckBoxState::Checked) { SwitchPreviewMode(true); } })[SNew(STextBlock).Text(LOCTEXT("ReplayMode", "结果回放"))]]
							+ SHorizontalBox::Slot().AutoWidth().Padding(0, 12, 0, 0)[SNew(SButton).Visibility_Lambda([this] { return bReplayRequested ? EVisibility::Visible : EVisibility::Collapsed; }).Text(LOCTEXT("Reinfer", "重新推理")).IsEnabled_Lambda([this] { return Animation.IsValid() && Model.IsValid(); }).OnClicked_Lambda([this] { StartReplayBuild(); return FReply::Handled(); })]
							+ SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)[SNew(STextBlock).Text_Lambda([this] { return ReplayStatusText(); }).ColorAndOpacity(Mint)]
						]
					]
					+ SVerticalBox::Slot().FillHeight(1)
					[
						SNew(SHorizontalBox)
						+ SHorizontalBox::Slot().FillWidth(1).Padding(0, 0, 10, 0)
						[
							SNew(SVerticalBox)
							+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 5)
							[
								SNew(SHorizontalBox)
								+ SHorizontalBox::Slot().FillWidth(1)[SNew(STextBlock).Text(LOCTEXT("SourceView", "● 源动画")).ColorAndOpacity(Blue)]
								+ SHorizontalBox::Slot().FillWidth(1)[SNew(STextBlock).Text(LOCTEXT("SoftView", "● GPU 软输出")).ColorAndOpacity(Orange)]
								+ SHorizontalBox::Slot().FillWidth(1)[SNew(STextBlock).Text(LOCTEXT("HardView", "● GPU + 硬参考")).ColorAndOpacity(Mint)]
							]
							+ SVerticalBox::Slot().FillHeight(1)
							[
								SNew(SBorder).BorderImage(&PanelBrush).Padding(5)[SAssignNew(Viewport, SAIAnimationPreviewViewport)]
							]
						]
						+ SHorizontalBox::Slot().AutoWidth()
						[
							SNew(SBox).WidthOverride(300)
							[
								SNew(SBorder).BorderImage(&PanelBrush).Padding(14)
								[
									SNew(SVerticalBox)
									+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 10)[SNew(STextBlock).Text(LOCTEXT("References", "硬姿态参考")).Font(FAppStyle::GetFontStyle("HeadingExtraSmall"))]
									+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 8)[SNew(STextBlock).Text(LOCTEXT("SourceFrames", "当前动画的源姿态帧；修改后立即更新预览。"))]
									+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 12)[SNew(SButton).ButtonColorAndOpacity(Mint).Text(LOCTEXT("AddCurrent", "+ 添加当前帧")).OnClicked(this, &SAIAnimationWorkbench::AddCurrentFrame)]
									+ SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 8)
									[
										SNew(SHorizontalBox)
										+ SHorizontalBox::Slot().FillWidth(1).Padding(0, 0, 4, 0)[SNew(SButton).Text(LOCTEXT("Undo", "撤销")).IsEnabled_Lambda([this] { return HistoryIndex > 0; }).OnClicked_Lambda([this] { RestoreHistory(-1); return FReply::Handled(); })]
										+ SHorizontalBox::Slot().FillWidth(1)[SNew(SButton).Text(LOCTEXT("Redo", "重做")).IsEnabled_Lambda([this] { return HistoryIndex + 1 < History.Num(); }).OnClicked_Lambda([this] { RestoreHistory(1); return FReply::Handled(); })]
									]
									+ SVerticalBox::Slot().FillHeight(1)[SNew(SScrollBox) + SScrollBox::Slot()[SAssignNew(ReferenceList, SVerticalBox)]]
									+ SVerticalBox::Slot().AutoHeight().Padding(0, 10, 0, 8)[SNew(STextBlock).Text(LOCTEXT("Model", "推理模型"))]
									+ SVerticalBox::Slot().AutoHeight()[SNew(SObjectPropertyEntryBox).AllowedClass(UAIAnimationModel::StaticClass()).ObjectPath_Lambda([this] { return Model.IsValid() ? Model->GetPathName() : FString(); }).OnObjectChanged_Lambda([this](const FAssetData& Asset) { Model.Reset(Cast<UAIAnimationModel>(Asset.GetAsset())); RefreshPreview(); })]
									+ SVerticalBox::Slot().AutoHeight().Padding(0, 14, 0, 0)[SNew(STextBlock).Text_Lambda([this] { return DiagnosticText(); }).AutoWrapText(true)]
									+ SVerticalBox::Slot().AutoHeight().Padding(0, 14, 0, 5)[SNew(STextBlock).Text(LOCTEXT("RootDataTitle", "Root 运动数据")).Font(FAppStyle::GetFontStyle("HeadingExtraSmall")).ColorAndOpacity(Mint)]
									+ SVerticalBox::Slot().AutoHeight()[SNew(STextBlock).Text_Lambda([this] { return Viewport->GetRootMetricsText(); }).AutoWrapText(true)]
								]
							]
						]
					]
					+ SVerticalBox::Slot().AutoHeight().Padding(0, 10, 0, 0)
					[
						SNew(SBorder).BorderImage(&PanelBrush).Padding(FMargin(14, 10))
						[
							SNew(SVerticalBox)
							+ SVerticalBox::Slot().AutoHeight()[SNew(STextBlock).Text_Lambda([this] { return TimeText(); })]
							+ SVerticalBox::Slot().AutoHeight().Padding(0, 5)
							[
						SNew(SSlider).PreventThrottling(true).IsEnabled_Lambda([this] { return !bBuildingCache && Animation.IsValid(); }).Value_Lambda([this] { return bScrubbing ? ScrubValue : Animation.IsValid() && Animation->GetPlayLength() > 0.0f ? Viewport->GetCurrentTime() / Animation->GetPlayLength() : 0.0f; })
				.OnMouseCaptureBegin_Lambda([this] { ScrubValue = Animation.IsValid() && Animation->GetPlayLength() > 0.0f ? Viewport->GetCurrentTime() / Animation->GetPlayLength() : 0.0f; bScrubbing = true; bPaused = true; Viewport->SetPaused(true); })
				.OnMouseCaptureEnd_Lambda([this] { bScrubbing = false; if (Animation.IsValid()) { Seek(ScrubValue * Animation->GetPlayLength(), true); } bPaused = true; Viewport->SetPaused(true); })
								.OnValueChanged(this, &SAIAnimationWorkbench::Scrub)
							]
							+ SVerticalBox::Slot().AutoHeight()
							[
								SNew(SHorizontalBox)
								+ SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 8, 0)[SNew(SButton).IsEnabled_Lambda([this] { return !bBuildingCache; }).Text(LOCTEXT("BackFrame", "◀ 1 帧")).OnClicked_Lambda([this] { Step(-1); return FReply::Handled(); })]
								+ SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 8, 0)[SNew(SButton).IsEnabled_Lambda([this] { return !bBuildingCache; }).Text_Lambda([this] { return bPaused ? LOCTEXT("Play", "▶ 播放") : LOCTEXT("Pause", "Ⅱ 暂停"); }).OnClicked_Lambda([this] { TogglePlayback(); return FReply::Handled(); })]
								+ SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 20, 0)[SNew(SButton).IsEnabled_Lambda([this] { return !bBuildingCache; }).Text(LOCTEXT("ForwardFrame", "1 帧 ▶")).OnClicked_Lambda([this] { Step(1); return FReply::Handled(); })]
								+ SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 14, 0)[SNew(SCheckBox).IsChecked_Lambda([this] { return bRootMotion ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }).OnCheckStateChanged_Lambda([this](ECheckBoxState State) { bRootMotion = State == ECheckBoxState::Checked; Viewport->SetRootMotion(bRootMotion); })[SNew(STextBlock).Text(LOCTEXT("RootMotion", "应用根运动"))]]
								+ SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 14, 0)[SNew(SCheckBox).IsChecked_Lambda([this] { return bTrajectory ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }).OnCheckStateChanged_Lambda([this](ECheckBoxState State) { bTrajectory = State == ECheckBoxState::Checked; Viewport->SetTrajectoryVisible(bTrajectory); })[SNew(STextBlock).Text(LOCTEXT("RootPath", "Root 轨迹"))]]
								+ SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 12, 0)[SNew(SCheckBox).IsChecked_Lambda([this] { return bBoneNames ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }).OnCheckStateChanged_Lambda([this](ECheckBoxState State) { bBoneNames = State == ECheckBoxState::Checked; Viewport->SetBoneNamesVisible(bBoneNames); })[SNew(STextBlock).Text(LOCTEXT("BoneNames", "骨骼名称"))]]
								+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0, 0, 5, 0)[SNew(STextBlock).Text(LOCTEXT("LabelTarget", "标注:"))]
								+ SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 4, 0)[SNew(SCheckBox).Style(FAppStyle::Get(), "RadioButton").IsChecked_Lambda([this] { return BoneLabelTarget == 0 ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }).OnCheckStateChanged_Lambda([this](ECheckBoxState State) { if (State == ECheckBoxState::Checked) { BoneLabelTarget = 0; Viewport->SetBoneLabelTarget(0); } })[SNew(STextBlock).Text(LOCTEXT("LabelSource", "源"))]]
								+ SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 4, 0)[SNew(SCheckBox).Style(FAppStyle::Get(), "RadioButton").IsChecked_Lambda([this] { return BoneLabelTarget == 1 ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }).OnCheckStateChanged_Lambda([this](ECheckBoxState State) { if (State == ECheckBoxState::Checked) { BoneLabelTarget = 1; Viewport->SetBoneLabelTarget(1); } })[SNew(STextBlock).Text(LOCTEXT("LabelSoft", "软"))]]
								+ SHorizontalBox::Slot().AutoWidth().Padding(12, 0, 0, 0)[SNew(SCheckBox).IsChecked_Lambda([this] { return bShowAllBoneLabels ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }).OnCheckStateChanged_Lambda([this](ECheckBoxState State) { bShowAllBoneLabels = State == ECheckBoxState::Checked; Viewport->SetBoneLabelOptions(BoneFilter, bShowAllBoneLabels); })[SNew(STextBlock).Text(LOCTEXT("AllBoneNames", "显示全部"))]]
								+ SHorizontalBox::Slot().AutoWidth().Padding(12, 0, 0, 0)[SNew(SBox).WidthOverride(155.0f)[SNew(SSearchBox).HintText(LOCTEXT("BoneSearch", "搜索骨骼名")).OnTextChanged_Lambda([this](const FText& Value) { BoneFilter = Value.ToString(); Viewport->SetBoneLabelOptions(BoneFilter, bShowAllBoneLabels); })]]
							]
							+ SVerticalBox::Slot().AutoHeight().Padding(0, 8, 0, 0)
							[
								SNew(SHorizontalBox)
				+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0, 0, 10, 0)[SNew(SCheckBox).IsChecked_Lambda([this] { return bLoopRange ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }).OnCheckStateChanged_Lambda([this](ECheckBoxState State) { bLoopRange = State == ECheckBoxState::Checked; RecalculateOutputFrames(); })[SNew(STextBlock).Text(LOCTEXT("LoopRange", "区间循环"))]]
								+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0, 0, 14, 0)[SNew(STextBlock).Text_Lambda([this] { return FText::FromString(FString::Printf(TEXT("源 %d 帧 · 30 FPS"), GetSourceFrameCount())); }).ColorAndOpacity(Blue)]
								+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0, 0, 5, 0)[SNew(STextBlock).Text(LOCTEXT("LoopStart", "起始帧"))]
								+ SHorizontalBox::Slot().AutoWidth().Padding(0, 12, 0, 0)[SNew(SBox).WidthOverride(72.0f)[SNew(SSpinBox<int32>).MinValue(0).MaxValue(100000).Value_Lambda([this] { return RangeStartFrame; }).OnValueCommitted_Lambda([this](int32 Value, ETextCommit::Type) { SetRange(Value, RangeEndFrame); })]]
								+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0, 0, 5, 0)[SNew(STextBlock).Text(LOCTEXT("LoopEnd", "结束帧"))]
								+ SHorizontalBox::Slot().AutoWidth().Padding(0, 16, 0, 0)[SNew(SBox).WidthOverride(72.0f)[SNew(SSpinBox<int32>).MinValue(1).MaxValue(100000).Value_Lambda([this] { return RangeEndFrame; }).OnValueCommitted_Lambda([this](int32 Value, ETextCommit::Type) { SetRange(RangeStartFrame, Value); })]]
								+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0, 0, 5, 0)[SNew(STextBlock).Text(LOCTEXT("Speed", "倍速"))]
								+ SHorizontalBox::Slot().AutoWidth().Padding(0, 7, 0, 0)[SNew(SBox).WidthOverride(78.0f)[SNew(SSpinBox<float>).MinValue(0.001f).MaxValue(1000.0f).MinSliderValue(0.05f).MaxSliderValue(4.0f).Delta(0.05f).Value_Lambda([this] { return SelectedSpeed; }).OnValueCommitted_Lambda([this](float Value, ETextCommit::Type) { SetSpeed(Value); })]]
								+ SHorizontalBox::Slot().AutoWidth().Padding(0, 8, 0, 0)
								[
									SNew(SComboBox<TSharedPtr<float>>).OptionsSource(&SpeedPresets)
									.OnGenerateWidget_Lambda([](TSharedPtr<float> Rate) { return StaticCastSharedRef<SWidget>(SNew(STextBlock).Text(FText::FromString(FString::Printf(TEXT("%.2fx"), *Rate)))); })
									.OnSelectionChanged_Lambda([this](TSharedPtr<float> Rate, ESelectInfo::Type) { if (Rate.IsValid()) { SetSpeed(*Rate); } })
									[SNew(STextBlock).Text(LOCTEXT("SpeedPresets", "预设 ▾"))]
								]
								+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(12, 0, 5, 0)[SNew(STextBlock).Text(LOCTEXT("OutputFps", "输出 FPS"))]
								+ SHorizontalBox::Slot().AutoWidth().Padding(0, 8, 0, 0)[SNew(SBox).WidthOverride(76.0f)[SNew(SSpinBox<int32>).MinValue(1).MaxValue(240).MinSliderValue(15).MaxSliderValue(120).Value_Lambda([this] { return OutputFps; }).OnValueCommitted_Lambda([this](int32 Value, ETextCommit::Type) { SetOutputFps(Value); })]]
								+ SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)[SNew(STextBlock).Text_Lambda([this] { return PlaybackSummaryText(); }).ColorAndOpacity(Mint)]
							]
						]
					]
				]
			];
			RefreshReferenceList();
			bValidateLive = FParse::Param(FCommandLine::Get(), TEXT("AIAnimationWorkbenchValidateLive"));
			Model.Reset(LoadObject<UAIAnimationModel>(nullptr, TEXT("/Game/AIAnimationPreview/Candidate24/DA_Reconstruction.DA_Reconstruction")));
			SelectAnimation(LoadObject<UAnimSequence>(nullptr, TEXT("/Game/Characters/UEFN_Mannequin/Animations/Traversal/Catch/Hurdle/M_Neutral_Traversal_Catch_Hurdle_low_run.M_Neutral_Traversal_Catch_Hurdle_low_run")));
			if (FParse::Param(FCommandLine::Get(), TEXT("AIAnimationWorkbenchAutoReinfer")))
			{
				bReplayRequested = true;
				StartReplayBuild();
			}
			else if (FParse::Param(FCommandLine::Get(), TEXT("AIAnimationWorkbenchAutoReplay")))
			{
				bReplayRequested = true;
				UpdateReplay(0.0f);
			}
		}

		virtual ~SAIAnimationWorkbench() override
		{
			if (IConsoleVariable* MaxFpsVariable = IConsoleManager::Get().FindConsoleVariable(TEXT("t.MaxFPS")))
			{
				MaxFpsVariable->Set(PreviousMaxFps, ECVF_SetByConsole);
			}
		}

		virtual void Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime) override
		{
			SCompoundWidget::Tick(AllottedGeometry, InCurrentTime, InDeltaTime);
			if (Viewport.IsValid())
			{
				if (bReplayRequested)
				{
					UpdateReplay(InDeltaTime);
				}
				else if (!bPaused && bLoopRange && Animation.IsValid())
				{
					const float SourceTime = Viewport->GetSourceTime();
					const float EndTime = FMath::Min(Animation->GetPlayLength() - 0.001f, RangeEndFrame / 30.0f + Viewport->GetDisplayDelay());
					if (SourceTime + 0.05f < LastSourceTime || SourceTime >= EndTime)
					{
						Seek(RangeStartFrame / 30.0f);
						bPaused = false;
						Viewport->SetPaused(false);
					}
					LastSourceTime = Viewport->GetSourceTime();
				}
			Viewport->ApplyRootMotion();
			if (bValidateLive && !bReplayRequested && Animation.IsValid())
			{
				const int32 Frame = FMath::RoundToInt(Viewport->GetCurrentTime() * 30.0f);
				if (DraftFrames.Contains(Frame) && !ValidatedLiveFrames.Contains(Frame))
				{
					Viewport->LogLiveAlignment(Frame);
					ValidatedLiveFrames.Add(Frame);
				}
			}
			}
		}

	private:
		int32 ActiveStartFrame() const { return bLoopRange ? RangeStartFrame : 0; }
		int32 ActiveEndFrame() const { return bLoopRange ? RangeEndFrame : GetSourceFrameCount(); }

		FString BuildReplayKey() const
		{
			if (!Animation.IsValid() || !Model.IsValid())
			{
				return FString();
			}
			auto AssetTime = [](const UObject* Asset) -> int64
			{
				const FString Filename = FPackageName::LongPackageNameToFilename(Asset->GetOutermost()->GetName(), TEXT(".uasset"));
				return IFileManager::Get().GetTimeStamp(*Filename).GetTicks();
			};
			auto CVarValue = [](const TCHAR* Name) -> int32
			{
				const IConsoleVariable* Variable = IConsoleManager::Get().FindConsoleVariable(Name);
				return Variable ? Variable->GetInt() : 0;
			};
			FString ReferenceFrames;
			for (const int32 Frame : DraftFrames)
			{
				ReferenceFrames += FString::Printf(TEXT("%d,"), Frame);
			}
			const FString RuntimeModule = FModuleManager::Get().GetModuleFilename(TEXT("AIAnimation"));
			const FString EditorModule = FModuleManager::Get().GetModuleFilename(TEXT("AIAnimationEditor"));
			const USkeletalMesh* PreviewMesh = Animation->GetSkeleton() ? Animation->GetSkeleton()->GetPreviewMesh(true) : nullptr;
			return FString::Printf(TEXT("v5|%s|%lld|%s|%lld|%s|%s|%lld|%lld|%lld|%d|%d|%d|%.9g|%d|%d|%d|%d|%s"),
				*Animation->GetPathName(), AssetTime(Animation.Get()), PreviewMesh ? *PreviewMesh->GetPathName() : TEXT(""), PreviewMesh ? AssetTime(PreviewMesh) : 0,
				*Model->GetPathName(), *Model->ModelSha256,
				AssetTime(Model.Get()), IFileManager::Get().GetTimeStamp(*RuntimeModule).GetTicks(), IFileManager::Get().GetTimeStamp(*EditorModule).GetTicks(),
				ActiveStartFrame(), ActiveEndFrame(), OutputFps, static_cast<double>(SelectedSpeed),
				CVarValue(TEXT("AIAnimation.Streaming")), CVarValue(TEXT("AIAnimation.DelayFrames")),
				CVarValue(TEXT("AIAnimation.Enabled")), CVarValue(TEXT("AIAnimation.HardReferences")), *ReferenceFrames);
		}

		void SwitchPreviewMode(bool bUseReplay)
		{
			const float SwitchTime = Viewport->GetCurrentTime();
			bReplayRequested = bUseReplay;
			bPaused = true;
			Viewport->SetPaused(true);
			if (!bUseReplay)
			{
				bBuildingCache = false;
				Viewport->FinishCacheBuild(nullptr);
				if (Animation.IsValid())
				{
					Viewport->Seek(SwitchTime, true);
				}
				return;
			}
			PendingReplayTimeSeconds = SwitchTime;
			UpdateReplay(0.0f);
		}

		void StartReplayBuild()
		{
			if (!Animation.IsValid() || !Model.IsValid())
			{
				return;
			}
			if (OutputFrames > 12000)
			{
				Cache.Reset(BuildReplayKey());
				Viewport->FinishCacheBuild(nullptr);
				ReplayMessage = LOCTEXT("ReplayTooLong", "结果超过 12000 帧；请缩短区间或提高倍速。");
				return;
			}
			ReplayMessage = FText::GetEmpty();
			PendingReplayTimeSeconds = Viewport->GetCurrentTime();
			Cache.Reset(BuildReplayKey());
			NextCacheFrame = 0;
			bBuildingCache = true;
			bPaused = true;
			Viewport->BeginCacheBuild(ActiveStartFrame() / 30.0f);
		}

		void UpdateReplay(float DeltaSeconds)
		{
			if (!Animation.IsValid() || !Model.IsValid())
			{
				ReplayMessage = LOCTEXT("ReplayNeedsAssets", "选择动画和推理模型后生成结果。");
				return;
			}
			const FString CurrentKey = BuildReplayKey();
			if (Cache.Key != CurrentKey)
			{
				bBuildingCache = false;
				if (Cache.Load(Animation->GetPathName(), CurrentKey, Viewport->GetPreviewBoneCount()))
				{
				UE_LOG(LogTemp, Display, TEXT("AIAnimationReplayCacheLoaded frames=%d bones=%d"), Cache.Frames.Num(), Viewport->GetPreviewBoneCount());
					Viewport->FinishCacheBuild(&Cache);
					Viewport->Seek(PendingReplayTimeSeconds);
					bPaused = true;
					Viewport->SetPaused(true);
				}
				else
				{
					StartReplayBuild();
				}
			}
			if (bBuildingCache)
			{
				if (NextCacheFrame < OutputFrames)
				{
					Cache.Frames.Add(Viewport->CaptureCacheFrame(NextCacheFrame, OutputFps, ActiveStartFrame() / 30.0f, SelectedSpeed));
					++NextCacheFrame;
				}
				if (NextCacheFrame >= OutputFrames)
				{
					if (!Cache.Save(Animation->GetPathName()))
					{
						ReplayMessage = LOCTEXT("ReplaySaveFailed", "结果已生成，但缓存文件保存失败。");
					}
					bBuildingCache = false;
					Viewport->FinishCacheBuild(&Cache);
					Viewport->Seek(PendingReplayTimeSeconds);
					bPaused = true;
				}
			}
			else
			{
				Viewport->TickReplay(DeltaSeconds, OutputFps);
			}
		}

		FText ReplayStatusText() const
		{
			if (!bReplayRequested)
			{
				return LOCTEXT("LiveModeHint", "当前连续执行 GPU 推理");
			}
			if (!ReplayMessage.IsEmpty())
			{
				return ReplayMessage;
			}
			if (bBuildingCache)
			{
				return FText::Format(LOCTEXT("ReplayBuilding", "正在推理并记录 {0} / {1} 帧"), FText::AsNumber(NextCacheFrame), FText::AsNumber(OutputFrames));
			}
			return FText::Format(LOCTEXT("ReplayReady", "最近一次结果 · {0} 帧 · 拖动或逐帧查看"), FText::AsNumber(Cache.Frames.Num()));
		}

		void SelectAnimation(UAnimSequence* NewAnimation)
		{
			Animation.Reset(NewAnimation);
			Status = FText::GetEmpty();
			ReferenceAsset.Reset();
			DraftFrames.Reset();
			SavedFrames.Reset();
			bDirty = false;
			bPaused = false;
			RangeStartFrame = 0;
			RangeEndFrame = NewAnimation ? FMath::Max(1, FMath::RoundToInt(NewAnimation->GetPlayLength() * 30.0f)) : 1;
			RecalculateOutputFrames();
			LastSourceTime = 0.0f;
			ValidatedLiveFrames.Reset();
			if (NewAnimation)
			{
				const FString PackagePath = ReferencePackagePath(NewAnimation);
				ReferenceAsset.Reset(LoadObject<UAIAnimationReferenceSet>(nullptr, *(PackagePath + TEXT(".") + FPackageName::GetShortName(PackagePath))));
				if (ReferenceAsset.IsValid() && ReferenceAsset->Animation.ToSoftObjectPath() == FSoftObjectPath(NewAnimation))
				{
					DraftFrames = ReferenceAsset->Frames;
					SavedFrames = DraftFrames;
				}
				else if (NewAnimation->GetName() == TEXT("M_Neutral_Traversal_Catch_Hurdle_low_run"))
				{
					DraftFrames = { 32, 34, 44, 52, 56, 59 };
					bDirty = true;
				}
			}
			History.Reset();
			History.Add(DraftFrames);
			HistoryIndex = 0;
			RefreshReferenceList();
			RefreshPreview();
		}

		void RefreshPreview()
		{
			if (Viewport.IsValid())
			{
				bBuildingCache = false;
				Viewport->FinishCacheBuild(nullptr);
				Cache.Reset(FString());
				Viewport->SetLiveFramesPerSecond(OutputFps);
				Viewport->SetPlaybackRate(GetEffectiveRate());
				Viewport->SetAssets(Animation.Get(), Model.Get(), DraftFrames);
				if (!bReplayRequested && Animation.IsValid())
				{
					Viewport->Seek(0.0f, true);
					Viewport->SetPaused(bPaused);
				}
			}
		}

		void RefreshReferenceList()
		{
			if (!ReferenceList.IsValid())
			{
				return;
			}
			ReferenceList->ClearChildren();
			for (int32 Frame : DraftFrames)
			{
				ReferenceList->AddSlot().AutoHeight().Padding(0, 0, 0, 6)
				[
					SNew(SBorder).BorderImage(&BackgroundBrush).Padding(6)
					[
						SNew(SHorizontalBox)
						+ SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)[SNew(SButton).Text(FText::Format(LOCTEXT("FrameEntry", "第 {0} 帧  ·  {1} 秒"), FText::AsNumber(Frame), FText::AsNumber(Frame / 30.0f))).OnClicked_Lambda([this, Frame] { Seek(Frame / 30.0f); return FReply::Handled(); })]
						+ SHorizontalBox::Slot().AutoWidth().Padding(5, 0, 0, 0)[SNew(SButton).Text(LOCTEXT("Delete", "删除")).OnClicked_Lambda([this, Frame] { DraftFrames.Remove(Frame); FramesChanged(); return FReply::Handled(); })]
					]
				];
			}
		}

		void InvalidateReplayCache()
		{
			bBuildingCache = false;
			Viewport->FinishCacheBuild(nullptr);
			Cache.Reset(FString());
		}

		void FramesChanged()
		{
			DraftFrames.Sort();
			History.SetNum(HistoryIndex + 1);
			History.Add(DraftFrames);
			++HistoryIndex;
			bDirty = DraftFrames != SavedFrames;
			Status = FText::GetEmpty();
			Viewport->SetReferenceFrames(DraftFrames);
			InvalidateReplayCache();
			RefreshReferenceList();
		}

		void RestoreHistory(int32 Offset)
		{
			HistoryIndex = FMath::Clamp(HistoryIndex + Offset, 0, History.Num() - 1);
			DraftFrames = History[HistoryIndex];
			bDirty = DraftFrames != SavedFrames;
			Viewport->SetReferenceFrames(DraftFrames);
			InvalidateReplayCache();
			RefreshReferenceList();
		}

		FReply AddCurrentFrame()
		{
			if (Animation.IsValid())
			{
				const int32 Frame = FMath::Clamp(FMath::RoundToInt(Viewport->GetCurrentTime() * 30.0f), 0, FMath::RoundToInt(Animation->GetPlayLength() * 30.0f));
				if (!DraftFrames.Contains(Frame))
				{
					DraftFrames.Add(Frame);
					FramesChanged();
				}
			}
			return FReply::Handled();
		}

		FReply SaveReferences()
		{
			if (!Animation.IsValid())
			{
				Status = LOCTEXT("ChooseAnimation", "请先选择动画。" );
				return FReply::Handled();
			}
			TSet<int32> SeenFrames;
			for (int32 Frame : DraftFrames)
			{
				if (Frame < 0 || Frame > FMath::RoundToInt(Animation->GetPlayLength() * 30.0f) || SeenFrames.Contains(Frame))
				{
					Status = LOCTEXT("InvalidFrames", "参考帧重复或超出动画范围；请修正后保存。" );
					return FReply::Handled();
				}
				SeenFrames.Add(Frame);
			}
			const FString PackagePath = ReferencePackagePath(Animation.Get());
			UPackage* Package = CreatePackage(*PackagePath);
			if (!ReferenceAsset.IsValid())
			{
				ReferenceAsset.Reset(NewObject<UAIAnimationReferenceSet>(Package, *FPackageName::GetShortName(PackagePath), RF_Public | RF_Standalone));
				FAssetRegistryModule::AssetCreated(ReferenceAsset.Get());
			}
			const FScopedTransaction Transaction(LOCTEXT("SaveReferencesTransaction", "保存动画硬姿态参考"));
			ReferenceAsset->Modify();
			ReferenceAsset->Animation = Animation.Get();
			ReferenceAsset->Frames = DraftFrames;
			ReferenceAsset->MarkPackageDirty();
			if (UEditorLoadingAndSavingUtils::SavePackages({ Package }, true))
			{
				bDirty = false;
				SavedFrames = DraftFrames;
				Status = FText::GetEmpty();
			}
			else
			{
				Status = LOCTEXT("SaveFailed", "保存失败；资产仍标记为未保存。" );
			}
			return FReply::Handled();
		}

		void Seek(float Seconds, bool bForceWarmup = false)
		{
			if (Animation.IsValid())
			{
				bPaused = true;
				Viewport->Seek(FMath::Clamp(Seconds, 0.0f, Animation->GetPlayLength()), bForceWarmup);
				LastSourceTime = Viewport->GetSourceTime();
				Status = FText::GetEmpty();
			}
		}

		int32 GetSourceFrameCount() const
		{
			return Animation.IsValid() ? FMath::Max(1, FMath::RoundToInt(Animation->GetPlayLength() * 30.0f)) : 1;
		}

		float GetEffectiveRate() const
		{
			return SelectedSpeed;
		}

		void RecalculateOutputFrames()
		{
			const double Duration = (ActiveEndFrame() - ActiveStartFrame()) / (30.0 * SelectedSpeed);
			OutputFrames = static_cast<int32>(FMath::Clamp<int64>(FMath::CeilToInt64(Duration * OutputFps), 1, 10000000));
			if (Viewport.IsValid())
			{
				Viewport->SetPlaybackRate(SelectedSpeed);
			}
		}

		void SetRange(int32 StartFrame, int32 EndFrame)
		{
			const bool bWasPaused = bPaused;
			const int32 LastFrame = GetSourceFrameCount();
			RangeStartFrame = FMath::Clamp(StartFrame, 0, LastFrame - 1);
			RangeEndFrame = FMath::Clamp(EndFrame, RangeStartFrame + 1, LastFrame);
			RecalculateOutputFrames();
			if (Animation.IsValid() && (Viewport->GetCurrentTime() < RangeStartFrame / 30.0f || Viewport->GetCurrentTime() >= RangeEndFrame / 30.0f))
			{
				Seek(RangeStartFrame / 30.0f);
				if (!bWasPaused)
				{
					bPaused = false;
					Viewport->SetPaused(false);
				}
			}
		}

		void SetSpeed(float Rate)
		{
			SelectedSpeed = FMath::Clamp(Rate, 0.001f, 1000.0f);
			RecalculateOutputFrames();
		}

		void SetOutputFps(int32 FramesPerSecond)
		{
			OutputFps = FMath::Clamp(FramesPerSecond, 1, 240);
			Viewport->SetLiveFramesPerSecond(OutputFps);
			if (IConsoleVariable* MaxFpsVariable = IConsoleManager::Get().FindConsoleVariable(TEXT("t.MaxFPS")))
			{
				MaxFpsVariable->Set(OutputFps, ECVF_SetByConsole);
			}
			RecalculateOutputFrames();
		}

		void TogglePlayback()
		{
			if (bPaused && Animation.IsValid() && bLoopRange && (Viewport->GetCurrentTime() < RangeStartFrame / 30.0f || Viewport->GetCurrentTime() >= RangeEndFrame / 30.0f))
			{
				Seek(RangeStartFrame / 30.0f);
			}
			bPaused = !bPaused;
			LastSourceTime = Viewport->GetSourceTime();
			Viewport->SetPaused(bPaused);
		}

		void Step(int32 Delta)
		{
			Seek(Viewport->GetCurrentTime() + Delta * SelectedSpeed / OutputFps);
		}

		void Scrub(float Fraction)
		{
			ScrubValue = Fraction;
			if (Animation.IsValid())
			{
				if (bScrubbing)
				{
					bPaused = true;
					Viewport->PreviewScrub(Fraction * Animation->GetPlayLength());
					Status = bReplayRequested ? LOCTEXT("ReplayScrub", "拖动中：正在查看已记录的推理帧。")
						: LOCTEXT("LiveScrub", "拖动中：姿态实时定位；松开后补齐 GPU 历史。");
				}
				else
				{
					Seek(Fraction * Animation->GetPlayLength());
				}
			}
		}

		FText TimeText() const
		{
			if (!Animation.IsValid())
			{
				return LOCTEXT("NoAnimation", "选择动画以开始预览");
			}
			const float SourceTime = Viewport->GetCurrentTime();
			const int32 OutputFrame = FMath::Clamp(FMath::RoundToInt((SourceTime - RangeStartFrame / 30.0f) * OutputFps / SelectedSpeed), 0, OutputFrames);
			return FText::Format(LOCTEXT("TimeFormat", "源第 {0} / {1} 帧 · {2} 秒    预览第 {3} / {4} 帧"), FText::AsNumber(FMath::RoundToInt(SourceTime * 30.0f)),
				FText::AsNumber(GetSourceFrameCount()), FText::AsNumber(SourceTime), FText::AsNumber(OutputFrame), FText::AsNumber(OutputFrames));
		}

		FText PlaybackSummaryText() const
		{
			return FText::FromString(FString::Printf(TEXT("预计 %d 帧 · %.2f 秒"), OutputFrames,
				(ActiveEndFrame() - ActiveStartFrame()) / (30.0f * SelectedSpeed)));
		}

		FText DiagnosticText() const
		{
			if (!Status.IsEmpty())
			{
				return Status;
			}
			if (Animation.IsValid() && !Model.IsValid())
			{
				return LOCTEXT("NeedModel", "请选择与动画骨架匹配的推理模型。" );
			}
			const FAIAnimationEvaluationStats* Stats = Viewport->GetHardStats();
			return Stats && Stats->NumQualitySamples > 0 ? FText::Format(LOCTEXT("Diagnostics", "GPU {0} ms · 姿态误差 {1} cm · 推理 {2} 次"),
				FText::AsNumber(Stats->LastInferenceMs), FText::AsNumber(Stats->LastJointErrorCm), FText::AsNumber(Stats->NumInferences)) : LOCTEXT("Warming", "等待模型预热和有效样本…");
		}

		TSharedPtr<SAIAnimationPreviewViewport> Viewport;
		TSharedPtr<SVerticalBox> ReferenceList;
		TStrongObjectPtr<UAnimSequence> Animation;
		TStrongObjectPtr<UAIAnimationModel> Model;
		TStrongObjectPtr<UAIAnimationReferenceSet> ReferenceAsset;
		TArray<int32> DraftFrames;
		TArray<int32> SavedFrames;
		TArray<TArray<int32>> History;
		int32 HistoryIndex = 0;
		FText Status;
		bool bDirty = false;
		bool bPaused = false;
		bool bRootMotion = false;
		bool bTrajectory = true;
		bool bBoneNames = true;
		int32 BoneLabelTarget = 2;
		bool bShowAllBoneLabels = false;
		FString BoneFilter;
		bool bScrubbing = false;
		float ScrubValue = 0.0f;
		TArray<TSharedPtr<float>> SpeedPresets;
		int32 RangeStartFrame = 0;
		int32 RangeEndFrame = 1;
		int32 OutputFrames = 1;
		int32 OutputFps = 30;
		float SelectedSpeed = 1.0f;
		float LastSourceTime = 0.0f;
		float PendingReplayTimeSeconds = 0.0f;
		float PreviousMaxFps = 0.0f;
		bool bLoopRange = true;
		bool bReplayRequested = false;
		bool bBuildingCache = false;
		bool bValidateLive = false;
		TSet<int32> ValidatedLiveFrames;
		int32 NextCacheFrame = 0;
		FAIAnimationPreviewCache Cache;
		FText ReplayMessage;
	};
}

TSharedRef<SWidget> CreateAIAnimationWorkbench()
{
	return SNew(SAIAnimationWorkbench);
}

#undef LOCTEXT_NAMESPACE
