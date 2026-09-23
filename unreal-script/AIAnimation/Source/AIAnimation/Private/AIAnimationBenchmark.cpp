// Copyright ZhaoZining. All Rights Reserved.

// 统计来自真实 Mesh 动画任务，首帧初始化和每次换动作的预热不纳入稳态结果。
#include "AIAnimationBenchmark.h"
#include "AIAnimationModel.h"
#include "AIAnimationSampling.h"
#include "AIAnimationPreviewInstance.h"
#include "Animation/AnimSequence.h"
#include "Camera/CameraComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformTLS.h"
#include "HAL/IConsoleManager.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"

AAIAnimationBenchmark::AAIAnimationBenchmark()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
	ReferenceMesh = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("Reference"));
	SoftMesh = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("Soft"));
	ReconstructedMesh = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("Reconstructed"));
	ReferenceMesh->SetupAttachment(RootComponent);
	SoftMesh->SetupAttachment(RootComponent);
	ReconstructedMesh->SetupAttachment(RootComponent);
	ReferenceMesh->SetRelativeLocation(FVector(-180, 0, 0));
	SoftMesh->SetRelativeLocation(FVector(0, 0, 0));
	ReconstructedMesh->SetRelativeLocation(FVector(180, 0, 0));
	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(RootComponent);
	Camera->SetRelativeLocation(FVector(390, 850, 230));
	Camera->SetRelativeRotation((FVector(0, 0, 100) - Camera->GetRelativeLocation()).Rotation());
	Camera->FieldOfView = 55.0f;
	ReferenceLabel = CreateDefaultSubobject<UTextRenderComponent>(TEXT("ReferenceLabel"));
	SoftLabel = CreateDefaultSubobject<UTextRenderComponent>(TEXT("SoftLabel"));
	ReconstructedLabel = CreateDefaultSubobject<UTextRenderComponent>(TEXT("ReconstructedLabel"));
	StatusLabel = CreateDefaultSubobject<UTextRenderComponent>(TEXT("StatusLabel"));
	for (UTextRenderComponent* Label : { ReferenceLabel.Get(), SoftLabel.Get(), ReconstructedLabel.Get(), StatusLabel.Get() })
	{
		Label->SetupAttachment(RootComponent);
		Label->SetHorizontalAlignment(EHTA_Center);
		Label->SetWorldSize(14.0f);
		Label->SetRelativeRotation(FRotator(0, 70, 0));
	}
	ReferenceLabel->SetRelativeLocation(FVector(-180, 0, 190));
	ReferenceLabel->SetText(FText::FromString(TEXT("SOURCE (TIME ALIGNED)")));
	ReferenceLabel->SetTextRenderColor(FColor(80, 200, 255));
	SoftLabel->SetRelativeLocation(FVector(0, 0, 190));
	SoftLabel->SetText(FText::FromString(TEXT("GPU SOFT")));
	SoftLabel->SetTextRenderColor(FColor(255, 170, 100));
	ReconstructedLabel->SetRelativeLocation(FVector(180, 0, 190));
	ReconstructedLabel->SetText(FText::FromString(TEXT("GPU + HARD REFERENCES")));
	ReconstructedLabel->SetTextRenderColor(FColor(80, 255, 170));
	StatusLabel->SetRelativeLocation(FVector(0, 0, 230));
	StatusLabel->SetWorldSize(9.0f);
}

void AAIAnimationBenchmark::BeginPlay()
{
	Super::BeginPlay();
	FParse::Value(FCommandLine::Get(), TEXT("AIAnimationBenchmarkOutput="), OutputDirectory);
	FString AnimationFilter;
	FParse::Value(FCommandLine::Get(), TEXT("AIAnimationAnimationFilter="), AnimationFilter);
	if (!AnimationFilter.IsEmpty())
	{
		Animations.RemoveAll([&AnimationFilter](const TObjectPtr<UAnimSequence>& Animation) { return !Animation || !Animation->GetName().Contains(AnimationFilter); });
	}
	FString ReferenceList;
	if (FParse::Value(FCommandLine::Get(), TEXT("AIAnimationReferenceFrames="), ReferenceList))
	{
		TArray<FString> Parts;
		ReferenceList.ParseIntoArray(Parts, TEXT("/"), true);
		for (const FString& Part : Parts)
		{
			if (Part.IsNumeric())
			{
				PreviewReferenceFrames.AddUnique(FCString::Atoi(*Part));
			}
		}
		PreviewReferenceFrames.Sort();
	}
	if (PreviewReferenceFrames.IsEmpty())
	{
		SoftMesh->SetVisibility(false);
		SoftMesh->SetComponentTickEnabled(false);
		SoftLabel->SetVisibility(false);
		ReferenceMesh->SetRelativeLocation(FVector(-120, 0, 0));
		ReconstructedMesh->SetRelativeLocation(FVector(120, 0, 0));
		ReconstructedLabel->SetRelativeLocation(FVector(120, 0, 190));
		ReconstructedLabel->SetText(FText::FromString(TEXT("GPU RECONSTRUCTION")));
		ReferenceLabel->SetRelativeLocation(FVector(-120, 0, 190));
	}
	if (!OutputDirectory.IsEmpty())
	{
		IFileManager::Get().MakeDirectory(*OutputDirectory, true);
	}
	for (USkeletalMeshComponent* Mesh : { ReferenceMesh.Get(), SoftMesh.Get(), ReconstructedMesh.Get() })
	{
		if (Mesh == SoftMesh && PreviewReferenceFrames.IsEmpty())
		{
			continue;
		}
		Mesh->SetSkeletalMesh(CharacterMesh);
		Mesh->SetAnimInstanceClass(UAIAnimationPreviewInstance::StaticClass());
		Mesh->SetForcedLOD(1);
		Mesh->bEnableUpdateRateOptimizations = false;
		Mesh->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
		Mesh->SetDisablePostProcessBlueprint(true);
		AddTickPrerequisiteComponent(Mesh);
	}
	if (APlayerController* Controller = GetWorld()->GetFirstPlayerController())
	{
		Controller->SetViewTarget(this);
	}
	ClipResults.SetNum(Animations.Num());
	StartSeconds = FPlatformTime::Seconds();
	SetAnimation(0);
}

void AAIAnimationBenchmark::SetAnimation(int32 Index)
{
	if (!Animations.IsValidIndex(Index))
	{
		return;
	}
	ActiveAnimation = Index;
	LastInferenceCount = 0;
	LastQualityCount = 0;
	LastSoftQualityCount = 0;
	const bool bRunReconstruction = FPlatformTime::Seconds() - StartSeconds >= 5.0;
	for (USkeletalMeshComponent* Mesh : { ReferenceMesh.Get(), SoftMesh.Get(), ReconstructedMesh.Get() })
	{
		if (Mesh == SoftMesh && PreviewReferenceFrames.IsEmpty())
		{
			continue;
		}
		UAIAnimationPreviewInstance* Instance = CastChecked<UAIAnimationPreviewInstance>(Mesh->GetAnimInstance());
		Instance->Sequence = Animations[Index];
		Instance->ReconstructionModel = Model.Get();
		Instance->bReferenceOnly = Mesh == ReferenceMesh;
		Instance->HardReferenceFrames = Mesh == ReconstructedMesh ? PreviewReferenceFrames : TArray<int32>();
		Instance->bReconstruct = bRunReconstruction;
		Instance->InitializeAnimation();
		Instance->EvaluationStats = {};
	}
}

void AAIAnimationBenchmark::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (bFinished || Animations.IsEmpty())
	{
		return;
	}
	const double Elapsed = FPlatformTime::Seconds() - StartSeconds;
	const double ActiveTime = FMath::Max(0.0, Elapsed - 5.0);
	const int32 Index = int32(ActiveTime / 6.0);
	if (Index >= Animations.Num())
	{
		if (OutputDirectory.IsEmpty())
		{
			InferenceTimes.Reset();
			EvaluationTimes.Reset();
			JointErrors.Reset();
			BaselineFrameTimes.Reset();
			ModelFrameTimes.Reset();
			WorkerThreadIds.Reset();
			ClipResults.Empty();
			ClipResults.SetNum(Animations.Num());
			StartSeconds = FPlatformTime::Seconds();
			SetAnimation(0);
			return;
		}
		SaveReport();
		bFinished = true;
		FPlatformMisc::RequestExit(false);
		return;
	}
	if (Index != ActiveAnimation)
	{
		SetAnimation(Index);
	}
	UAIAnimationPreviewInstance* Instance = CastChecked<UAIAnimationPreviewInstance>(ReconstructedMesh->GetAnimInstance());
	UAIAnimationPreviewInstance* SoftInstance = Cast<UAIAnimationPreviewInstance>(SoftMesh->GetAnimInstance());
	Instance->bReconstruct = Elapsed >= 5.0;
	const FAIAnimationEvaluationStats& Stats = Instance->EvaluationStats;
	if (SoftInstance)
	{
		SoftInstance->bReconstruct = Instance->bReconstruct;
	}
	const FAIAnimationEvaluationStats SoftStats = SoftInstance ? SoftInstance->EvaluationStats : FAIAnimationEvaluationStats{};
	FClipResult& Clip = ClipResults[Index];
	// 换动作的这个 Tick 尚未得到新动画任务结果，不能把上一个动作的快照记入新动作。
	const bool bFresh = Stats.NumInferences > LastInferenceCount && Stats.bInferredThisEvaluation;
	Clip.Failures = FMath::Max(Clip.Failures, Stats.NumFailures);
	Clip.Fallbacks = FMath::Max(Clip.Fallbacks, Stats.NumFallbacks);
	Clip.GameThreadSkips = FMath::Max(Clip.GameThreadSkips, Stats.NumGameThreadSkips);
	Clip.Discontinuities = FMath::Max(Clip.Discontinuities, Stats.NumDiscontinuities);
	if (Elapsed > 2.0 && Elapsed < 5.0)
	{
		BaselineFrameTimes.Add(DeltaSeconds * 1000.0);
	}
	const double ClipTime = FMath::Fmod(ActiveTime, 6.0);
	if (Elapsed >= 5.0 && ClipTime > 2.0)
	{
		ModelFrameTimes.Add(DeltaSeconds * 1000.0);
		if (bFresh)
		{
			InferenceTimes.Add(Stats.LastInferenceMs);
			Clip.InferenceTimes.Add(Stats.LastInferenceMs);

			EvaluationTimes.Add(Stats.LastEvaluationMs);

			WorkerThreadIds.Add(Stats.LastThreadId);
		}
	}
	if (Elapsed >= 5.0 && ClipTime > 2.0 && Stats.NumQualitySamples > LastQualityCount)
	{
		Clip.JointErrors.Add(Stats.LastJointErrorCm);
		Clip.RotationErrors.Add(Stats.LastRotationErrorDegrees);
		JointErrors.Add(Stats.LastJointErrorCm);
		if (Stats.bTemporalMetricValid)
		{
			Clip.ModelAccelerations.Add(Stats.LastModelAcceleration);
			Clip.SourceAccelerations.Add(Stats.LastSourceAcceleration);
			Clip.VelocityErrors.Add(Stats.LastVelocityError);
		}
	}
	if (Elapsed >= 5.0 && ClipTime > 2.0 && SoftStats.NumQualitySamples > LastSoftQualityCount)
	{
		Clip.SoftJointErrors.Add(SoftStats.LastJointErrorCm);
	}
	if (Elapsed >= 5.0 && Stats.NumQualitySamples > LastQualityCount && Stats.bLastQualityIsHardReference)
	{
		Clip.HardReferenceErrors.Add(Stats.LastJointErrorCm);
	}
	LastQualityCount = Stats.NumQualitySamples;
	LastSoftQualityCount = SoftStats.NumQualitySamples;
	LastInferenceCount = Stats.NumInferences;
	StatusLabel->SetText(FText::FromString(FString::Printf(TEXT("%s\nGPU %.2f ms | error %.2f cm | %llu runs"), *Animations[Index]->GetName(), Stats.LastInferenceMs, Stats.LastJointErrorCm, Stats.NumInferences)));
	if (!OutputDirectory.IsEmpty() && Elapsed >= 5.0 && ClipTime > 3.0 && CapturedAnimation != Index)
	{
		CapturedAnimation = Index;
		FScreenshotRequest::RequestScreenshot(OutputDirectory / FString::Printf(TEXT("clip_%02d.png"), Index), false, false);
	}
}

void AAIAnimationBenchmark::SaveReport()
{
	TSharedRef<FJsonObject> Report = MakeShared<FJsonObject>();
	Report->SetStringField(TEXT("scope"), TEXT("GASP source animation and DirectML reconstruction on animation worker; reference anchors use the source pose in this controlled preview"));
	TArray<TSharedPtr<FJsonValue>> ReferenceFramesJson;
	for (int32 ReferenceFrame : PreviewReferenceFrames)
	{
		ReferenceFramesJson.Add(MakeShared<FJsonValueNumber>(ReferenceFrame));
	}
	Report->SetArrayField(TEXT("hard_reference_frames"), ReferenceFramesJson);
	Report->SetStringField(TEXT("model"), GetPathNameSafe(Model));
	Report->SetStringField(TEXT("gpu"), GRHIAdapterName);
	Report->SetNumberField(TEXT("game_thread_id"), FPlatformTLS::GetCurrentThreadId());
	const FAIAnimationEvaluationStats& FinalStats = CastChecked<UAIAnimationPreviewInstance>(ReconstructedMesh->GetAnimInstance())->EvaluationStats;
	Report->SetNumberField(TEXT("delay_frames"), FinalStats.DelayFrames);
	Report->SetNumberField(TEXT("inference_stride"), FinalStats.InferenceStride);
	Report->SetStringField(TEXT("quality_timebase"), TEXT("30 Hz source-aligned playback samples; acceleration cm/frame^2, velocity error cm/frame, local rotation error degrees; excludes warmup/crossfade"));
	Report->SetNumberField(TEXT("window_frames"), Model ? Model->WindowFrames : 0);
	Report->SetStringField(TEXT("model_sha256"), Model ? Model->ModelSha256 : FString());
	uint64 TotalFailures = 0;
	uint64 TotalFallbacks = 0;
	uint64 TotalSkips = 0;
	bool bPassed = !ClipResults.IsEmpty() && !WorkerThreadIds.Contains(FPlatformTLS::GetCurrentThreadId());
	TArray<TSharedPtr<FJsonValue>> Clips;
	for (int32 Index = 0; Index < ClipResults.Num(); ++Index)
	{
		const FClipResult& Clip = ClipResults[Index];
		TotalFailures += Clip.Failures;
		TotalFallbacks += Clip.Fallbacks;
		TotalSkips += Clip.GameThreadSkips;
		const bool bClipPassed = AIAnimationSampling::Passed(Clip.JointErrors.Num(), Clip.Failures, Clip.Fallbacks, Clip.GameThreadSkips) && Clip.InferenceTimes.Num() >= 5;
		bPassed &= bClipPassed;
		TSharedRef<FJsonObject> Item = MakeShared<FJsonObject>();
		Item->SetStringField(TEXT("asset"), GetPathNameSafe(Animations[Index]));
		Item->SetBoolField(TEXT("passed"), bClipPassed);
		Item->SetNumberField(TEXT("samples"), Clip.InferenceTimes.Num());
		Item->SetNumberField(TEXT("quality_samples"), Clip.JointErrors.Num());
		Item->SetNumberField(TEXT("failures"), Clip.Failures);
		Item->SetNumberField(TEXT("fallbacks"), Clip.Fallbacks);
		Item->SetNumberField(TEXT("game_thread_skips"), Clip.GameThreadSkips);
		Item->SetNumberField(TEXT("loop_resets"), Clip.Discontinuities);
		const auto AddClipMetric = [&Item](const TCHAR* Name, const TArray<double>& Values)
		{
			if (Values.IsEmpty())
			{
				return;
			}
			double Sum = 0.0;
			TArray<double> Sorted = Values;
			Sorted.Sort();
			for (double Value : Values)
			{
				Sum += Value;
			}
			TSharedRef<FJsonObject> Metric = MakeShared<FJsonObject>();
			Metric->SetNumberField(TEXT("count"), Values.Num());
			Metric->SetNumberField(TEXT("mean"), Sum / Values.Num());
			Metric->SetNumberField(TEXT("p95"), Sorted[FMath::FloorToInt((Sorted.Num() - 1) * .95)]);
			Item->SetObjectField(Name, Metric);
		};
		AddClipMetric(TEXT("gpu_sync_ms"), Clip.InferenceTimes);
		AddClipMetric(TEXT("joint_rmse_cm"), Clip.JointErrors);
		AddClipMetric(TEXT("soft_joint_rmse_cm"), Clip.SoftJointErrors);
		AddClipMetric(TEXT("hard_reference_rmse_cm"), Clip.HardReferenceErrors);
		AddClipMetric(TEXT("model_acceleration"), Clip.ModelAccelerations);
		AddClipMetric(TEXT("source_acceleration"), Clip.SourceAccelerations);
		AddClipMetric(TEXT("velocity_error"), Clip.VelocityErrors);
		AddClipMetric(TEXT("rotation_error_degrees"), Clip.RotationErrors);
		Clips.Add(MakeShared<FJsonValueObject>(Item));
	}
	Report->SetNumberField(TEXT("failures"), TotalFailures);
	Report->SetNumberField(TEXT("fallbacks"), TotalFallbacks);
	Report->SetNumberField(TEXT("game_thread_skips"), TotalSkips);
	Report->SetArrayField(TEXT("clips"), Clips);
	Report->SetBoolField(TEXT("passed"), bPassed);
	TArray<TSharedPtr<FJsonValue>> ThreadIds;
	for (uint32 ThreadId : WorkerThreadIds)
	{
		ThreadIds.Add(MakeShared<FJsonValueNumber>(ThreadId));
	}
	Report->SetArrayField(TEXT("animation_worker_thread_ids"), ThreadIds);
	const auto AddMetric = [&Report](const FString& Name, TArray<double> Values)
	{
		TSharedRef<FJsonObject> Metric = MakeShared<FJsonObject>();
		Metric->SetNumberField(TEXT("count"), Values.Num());
		if (!Values.IsEmpty())
		{
			Values.Sort();
			double Sum = 0.0;
			for (double Value : Values)
			{
				Sum += Value;
			}
			Metric->SetNumberField(TEXT("mean"), Sum / Values.Num());
			Metric->SetNumberField(TEXT("p50"), Values[FMath::FloorToInt((Values.Num() - 1) * .5)]);
			Metric->SetNumberField(TEXT("p95"), Values[FMath::FloorToInt((Values.Num() - 1) * .95)]);
			Metric->SetNumberField(TEXT("p99"), Values[FMath::FloorToInt((Values.Num() - 1) * .99)]);
		}
		Report->SetObjectField(Name, Metric);
	};
	AddMetric(TEXT("gpu_sync_ms"), InferenceTimes);
	AddMetric(TEXT("reconstruction_evaluation_ms"), EvaluationTimes);
	AddMetric(TEXT("source_joint_rmse_cm"), JointErrors);
	AddMetric(TEXT("baseline_frame_ms"), BaselineFrameTimes);
	AddMetric(TEXT("model_frame_ms"), ModelFrameTimes);
	FString Json;
	FJsonSerializer::Serialize(Report, TJsonWriterFactory<>::Create(&Json));
	FFileHelper::SaveStringToFile(Json, *(OutputDirectory / TEXT("runtime_report.json")), FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
	UE_LOG(LogAnimation, Display, TEXT("AIAnimation benchmark: %s"), *Json);
}
