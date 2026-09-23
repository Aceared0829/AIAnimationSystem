// Copyright ZhaoZining. All Rights Reserved.

// 只在 PreUpdate 访问 UObject；Evaluate 使用独占数值状态并保留源 Root 的移动权威。
#include "AnimNode_AIAnimation.h"
#include "AIAnimationGpuSession.h"
#include "AIAnimationSampling.h"
#include "AIAnimationPoseBuffer.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "Components/SkeletalMeshComponent.h"
#include "HAL/PlatformTLS.h"
#include "HAL/IConsoleManager.h"
#include "ProfilingDebugging/CpuProfilerTrace.h"
#include "ProfilingDebugging/CsvProfiler.h"

CSV_DEFINE_CATEGORY(AIAnimation, true);
static TAutoConsoleVariable<int32> CVarAIAnimationStreaming(TEXT("AIAnimation.Streaming"), 1, TEXT("0 为末帧对照，1 为固定步长重叠播放。"));
static TAutoConsoleVariable<int32> CVarAIAnimationDelay(TEXT("AIAnimation.DelayFrames"), 8, TEXT("重叠播放延迟，支持 4、8 或 12 个 30 Hz 采样帧。"));
static TAutoConsoleVariable<int32> CVarAIAnimationEnabled(TEXT("AIAnimation.Enabled"), 1, TEXT("0 回退源姿态，1 启用模型重建。"));
static TAutoConsoleVariable<int32> CVarAIAnimationHardReferences(TEXT("AIAnimation.HardReferences"), 1, TEXT("预览台：1 将手选源帧作为硬约束，0 查看同一窗口模型软输出。"));
static TAutoConsoleVariable<int32> CVarAIAnimationDebugTime(TEXT("AIAnimation.DebugTime"), 0, TEXT("1 记录预览硬参考附近的源采样时间与播放位置。"));

void FAnimNode_AIAnimation::Initialize_AnyThread(const FAnimationInitializeContext& Context)
{
	FAnimNode_Base::Initialize_AnyThread(Context);
	Source.Initialize(Context);
	Stats = {};
	Playback = MakeShared<FAIAnimationPoseBuffer>();
	ResetHistory();
	bMapped = false;
}

void FAnimNode_AIAnimation::CacheBones_AnyThread(const FAnimationCacheBonesContext& Context)
{
	Source.CacheBones(Context);
	bMapped = false;
	ResetHistory();
}

void FAnimNode_AIAnimation::PreUpdate(const UAnimInstance* InAnimInstance)
{
	if (LoadedModel.Get() != Model || bLoadedReferenceOnly != bReferenceOnly)
	{
		Session.Reset();
		LoadedModel = Model;
		bLoadedReferenceOnly = bReferenceOnly;
		bMapped = false;
		bResetRequested = true;
		if (Model)
		{
			FString Error;
			Session = FAIAnimationGpuSession::Create(*Model, Error, !bReferenceOnly);
			if (!Session)
			{
				UE_LOG(LogAnimation, Error, TEXT("AIAnimation: %s"), *Error);
			}
		}
	}
	if (const USkeletalMeshComponent* Mesh = InAnimInstance->GetSkelMeshComponent())
	{
		const FVector Location = Mesh->GetComponentLocation();
		bResetRequested |= bHasWorldLocation && FVector::DistSquared(Location, PreviousWorldLocation) > FMath::Square(300.0);
		PreviousWorldLocation = Location;
		bHasWorldLocation = true;
	}
}

void FAnimNode_AIAnimation::Update_AnyThread(const FAnimationUpdateContext& Context)
{
	GetEvaluateGraphExposedInputs().Execute(Context);
	Source.Update(Context);
	const bool bNewStreaming = CVarAIAnimationStreaming.GetValueOnAnyThread() != 0;
	const int32 RequestedDelay = CVarAIAnimationDelay.GetValueOnAnyThread();
	const int32 NewDelay = RequestedDelay <= 4 ? 4 : RequestedDelay <= 8 ? 8 : 12;
	if (bNewStreaming != bStreaming || NewDelay != ActiveDelayFrames)
	{
		bStreaming = bNewStreaming;
		ActiveDelayFrames = NewDelay;
		bResetRequested = true;
	}
	Stats.DelayFrames = bStreaming ? ActiveDelayFrames : 0;
	Stats.InferenceStride = bStreaming ? 4 : 1;
	if (Context.GetDeltaTime() > 0.25f || bResetRequested || !bEnabled || Alpha <= 0.0f || CVarAIAnimationEnabled.GetValueOnAnyThread() == 0)
	{
		ResetHistory();
		bResetRequested = false;
	}
	AccumulatedSeconds += Context.GetDeltaTime();
}

void FAnimNode_AIAnimation::ResetHistory()
{
	NumHistoryFrames = 0;
	AccumulatedSeconds = 0.0f;
	SampleRemainderSeconds = 0.0;
	bHasPreviousSourcePose = false;
	SampleIndex = -1;
	ModelBlend = 0.0;
	LastQualityIndex = -1;
	PreviousModelPositions.Reset();
	OlderModelPositions.Reset();
	PreviousSourcePositions.Reset();
	OlderSourcePositions.Reset();
	// 跳帧、换动作和循环回绕都经过这里；旧动作的显示姿态不能混入新时间段。
	LastDisplayed.Reset();
	TransitionFrom.Reset();
	TransitionSeconds = 1.0;
	if (Playback)
	{
		Playback->Reset();
	}
}

void FAnimNode_AIAnimation::ResetSamplingHistory()
{
	ResetHistory();
	++Stats.NumDiscontinuities;
}

bool FAnimNode_AIAnimation::MapBones(const FBoneContainer& RequiredBones)
{
	BoneIndices.Reset();
	FBoneReference RootReference;
	RootReference.BoneName = Session->RootBone;
	RootReference.Initialize(RequiredBones);
	if (!RootReference.IsValidToEvaluate(RequiredBones))
	{
		return false;
	}
	RootIndex = RootReference.GetCompactPoseIndex(RequiredBones);
	for (const FAIAnimationBone& Bone : Session->Bones)
	{
		FBoneReference Reference;
		Reference.BoneName = Bone.Name;
		Reference.Initialize(RequiredBones);
		if (!Reference.IsValidToEvaluate(RequiredBones))
		{
			return false;
		}
		const FCompactPoseBoneIndex Index = Reference.GetCompactPoseIndex(RequiredBones);
		const FCompactPoseBoneIndex ExpectedParent = Bone.ParentIndex == INDEX_NONE ? RootIndex : BoneIndices[Bone.ParentIndex];
		if (RequiredBones.GetParentBoneIndex(Index) != ExpectedParent)
		{
			return false;
		}
		const FTransform ExpectedLocal = Bone.ParentIndex == INDEX_NONE ? Bone.ReferenceTransform : Bone.ReferenceTransform.GetRelativeTransform(Session->Bones[Bone.ParentIndex].ReferenceTransform);
		const FTransform& MeshLocal = RequiredBones.GetRefPoseTransform(Index);
		if (!MeshLocal.GetTranslation().Equals(ExpectedLocal.GetTranslation(), 0.1) || MeshLocal.GetRotation().AngularDistance(ExpectedLocal.GetRotation()) > FMath::DegreesToRadians(0.1))
		{
			return false;
		}
		BoneIndices.Add(Index);
	}
	History.SetNumZeroed((Session->WindowFrames + 1) * BoneIndices.Num() * 12);
	if (CVarAIAnimationDebugTime.GetValueOnAnyThread() != 0 && !HardReferenceFrames.IsEmpty())
	{
		UE_LOG(LogTemp, Display, TEXT("AIAnimationBoneMap bones=%d required=%d"), BoneIndices.Num(), RequiredBones.GetNumBones());
	}
	bMapped = true;
	return true;
}

void FAnimNode_AIAnimation::Evaluate_AnyThread(FPoseContext& Output)
{
	Source.Evaluate(Output);
	Stats.bInferredThisEvaluation = false;
	TRACE_CPUPROFILER_EVENT_SCOPE(AIAnimation_ReconstructPose);
	const double EvaluationStart = FPlatformTime::Seconds();
	const double DeltaSeconds = AccumulatedSeconds;
	if (!bEnabled || !FMath::IsFinite(Alpha) || Alpha <= 0.0f || CVarAIAnimationEnabled.GetValueOnAnyThread() == 0)
	{
		return;
	}
	if (!Session)
	{
		++Stats.NumFallbacks;
		return;
	}
	if (IsInGameThread() && !bAllowGameThreadInference)
	{
		++Stats.NumGameThreadSkips;
		return;
	}
	if (!bMapped && !MapBones(Output.Pose.GetBoneContainer()))
	{
		++Stats.NumFallbacks;
		return;
	}
	FCSPose<FCompactPose> ComponentPose;
	ComponentPose.InitPose(Output.Pose);
	const FTransform RootTransform = ComponentPose.GetComponentSpaceTransform(RootIndex);
	const int32 NumBones = BoneIndices.Num();
	const int32 FrameValues = NumBones * 12;
	TArray<FTransform> CurrentSourcePose;
	CurrentSourcePose.SetNum(NumBones);
	for (int32 BoneIndex = 0; BoneIndex < NumBones; ++BoneIndex)
	{
		CurrentSourcePose[BoneIndex] = ComponentPose.GetComponentSpaceTransform(BoneIndices[BoneIndex]).GetRelativeTransform(RootTransform);
		if (CurrentSourcePose[BoneIndex].ContainsNaN())
		{
			++Stats.NumFailures;
			ResetHistory();
			return;
		}
	}
	TArray<double> Fractions;
	if (!bHasPreviousSourcePose)
	{
		PreviousSourcePose = CurrentSourcePose;
		bHasPreviousSourcePose = true;
		Fractions.Add(1.0);
	}
	else
	{
		AIAnimationSampling::Advance(AccumulatedSeconds, Session->SampleRate, SampleRemainderSeconds, Fractions);
	}
	AccumulatedSeconds = 0.0;
	for (int32 FractionIndex = 0; FractionIndex < Fractions.Num(); ++FractionIndex)
	{
		const double Fraction = Fractions[FractionIndex];
		if (NumHistoryFrames == Session->WindowFrames)
		{
			FMemory::Memmove(History.GetData(), History.GetData() + FrameValues, (Session->WindowFrames - 1) * FrameValues * sizeof(float));
		}
		else
		{
			++NumHistoryFrames;
		}
		float* Sample = History.GetData() + (NumHistoryFrames - 1) * FrameValues;
		TArray<FTransform> SampleComponent;
		SampleComponent.SetNum(NumBones);
		for (int32 BoneIndex = 0; BoneIndex < NumBones; ++BoneIndex)
		{
			FTransform Relative;
			Relative.Blend(PreviousSourcePose[BoneIndex], CurrentSourcePose[BoneIndex], Fraction);
			SampleComponent[BoneIndex] = Relative;
			const FVector Position = Relative.GetTranslation();
			Sample[BoneIndex * 12] = Position.X;
			Sample[BoneIndex * 12 + 1] = Position.Y;
			Sample[BoneIndex * 12 + 2] = Position.Z;
			const FQuat Rotation = Relative.GetRotation();
			for (int32 Axis = 0; Axis < 3; ++Axis)
			{
				FVector Unit = FVector::ZeroVector;
				Unit[Axis] = 1.0;
				const FVector Column = Rotation.RotateVector(Unit);
				for (int32 Row = 0; Row < 3; ++Row)
				{
					Sample[BoneIndex * 12 + 3 + Row * 3 + Axis] = Column[Row];
				}
			}
		}
		TArray<FTransform> SampleLocal;
		ToLocal(SampleComponent, SampleLocal);
		const double SampleAssetTime = PreviousAssetTimeSeconds < 0.0f ? CurrentAssetTimeSeconds
			: FMath::Lerp(double(PreviousAssetTimeSeconds), double(CurrentAssetTimeSeconds), Fraction);
		const int32 AssetFrame = SampleAssetTime >= 0.0 ? FMath::RoundToInt(SampleAssetTime * Session->SampleRate) : INDEX_NONE;
		Playback->AddSource(++SampleIndex, SampleLocal, AssetFrame, SampleAssetTime);
		if (!bReferenceOnly && NumHistoryFrames == Session->WindowFrames && (!bStreaming || (SampleIndex - Session->WindowFrames + 1) % 4 == 0))
		{
			FMemory::Memcpy(History.GetData() + Session->WindowFrames * FrameValues, Sample, FrameValues * sizeof(float));
			if (!InferWindow(SampleIndex))
			{
				++Stats.NumFailures;
				ResetHistory();
				return;
			}
		}
	}
	PreviousSourcePose = MoveTemp(CurrentSourcePose);
	const double RawPosition = bStreaming ? FMath::Clamp(SampleIndex + SampleRemainderSeconds * Session->SampleRate - ActiveDelayFrames, 0.0, double(SampleIndex)) : double(SampleIndex);
	const double NearestSample = static_cast<double>(FMath::RoundToInt64(RawPosition));
	// 世界时间累积的微小尾数不应让整帧读取要求尚未到达的下一采样帧。
	const double Position = FMath::Abs(RawPosition - NearestSample) < 0.0001 ? NearestSample : RawPosition;
	if (bStreaming)
	{
		Playback->StabilizeStationary(Position);
	}
	bool bReady = false;
	TArray<FTransform> Display;
	const TConstArrayView<int32> ActiveReferences = CVarAIAnimationHardReferences.GetValueOnAnyThread() != 0 ? TConstArrayView<int32>(HardReferenceFrames) : TConstArrayView<int32>();
	if (!Playback->Read(Position, bReferenceOnly, ModelBlend, Display, bReady, ActiveReferences))
	{
		++Stats.NumFallbacks;
		return;
	}
	if (CVarAIAnimationDebugTime.GetValueOnAnyThread() != 0 && !HardReferenceFrames.IsEmpty())
	{
		const FAIAnimationBufferedPose* DisplaySample = Playback->Find(FMath::FloorToInt64(Position));
		if (DisplaySample && (DisplaySample->Index == 0 || HardReferenceFrames.Contains(DisplaySample->AssetFrame)))
		{
			UE_LOG(LogTemp, Display, TEXT("AIAnimationTime source=%.6f displaySample=%lld asset=%.6f frame=%d position=%.6f ready=%d blend=%.3f"),
				CurrentAssetTimeSeconds, DisplaySample->Index, DisplaySample->AssetTimeSeconds, DisplaySample->AssetFrame, Position, bReady, ModelBlend);
		}
	}
	ModelBlend = bReady ? FMath::Min(1.0, ModelBlend + DeltaSeconds / 0.15) : 0.0;
	Playback->Read(Position, bReferenceOnly, bStreaming ? ModelBlend : 1.0, Display, bReady, ActiveReferences);
	TransitionSeconds += DeltaSeconds;
	if (bStreaming && TransitionSeconds < 0.1 && TransitionFrom.Num() == Display.Num())
	{
		for (int32 Bone = 0; Bone < Display.Num(); ++Bone)
		{
			Display[Bone].Blend(TransitionFrom[Bone], Display[Bone], TransitionSeconds / 0.1);
		}
	}
	for (int32 Bone = 0; Bone < NumBones; ++Bone)
	{
		FTransform Blended;
		Blended.Blend(Output.Pose[BoneIndices[Bone]], Display[Bone], FMath::Clamp(Alpha, 0.0f, 1.0f));
		Blended.SetScale3D(Output.Pose[BoneIndices[Bone]].GetScale3D());
		Output.Pose[BoneIndices[Bone]] = Blended;
	}
	LastDisplayed = MoveTemp(Display);
	if (!bReferenceOnly && bReady && (!bStreaming || (ModelBlend >= 1.0 && TransitionSeconds >= 0.1)))
	{
		MeasureQuality(FMath::FloorToInt64(Position));
	}
	Playback->Commit(Position);
	Stats.LastEvaluationMs = (FPlatformTime::Seconds() - EvaluationStart) * 1000.0;
	CSV_CUSTOM_STAT(AIAnimation, EvaluationMs, Stats.LastEvaluationMs, ECsvCustomStatOp::Accumulate);
}

void FAnimNode_AIAnimation::ToLocal(TConstArrayView<FTransform> Component, TArray<FTransform>& Local) const
{
	Local.SetNum(Component.Num());
	for (int32 Bone = 0; Bone < Component.Num(); ++Bone)
	{
		const int32 Parent = Session->Bones[Bone].ParentIndex;
		Local[Bone] = Parent == INDEX_NONE ? Component[Bone] : Component[Bone].GetRelativeTransform(Component[Parent]);
	}
}

bool FAnimNode_AIAnimation::InferWindow(int64 LastSample)
{
	for (float Value : History)
	{
		if (!FMath::IsFinite(Value))
		{
			return false;
		}
	}
	if (!Session->Run(History, Stats.LastInferenceMs, bAllowGameThreadInference))
	{
		return false;
	}
	++Stats.NumInferences;
	Stats.bInferredThisEvaluation = true;
	Stats.LastThreadId = FPlatformTLS::GetCurrentThreadId();
	CSV_CUSTOM_STAT(AIAnimation, GpuSyncMs, Stats.LastInferenceMs, ECsvCustomStatOp::Accumulate);
	CSV_CUSTOM_STAT(AIAnimation, InferenceCount, 1, ECsvCustomStatOp::Accumulate);
	const int32 NumBones = BoneIndices.Num();
	TArray<FTransform> Window;
	TArray<FTransform> Component;
	Component.SetNum(NumBones);
	for (int32 Frame = 0; Frame < Session->WindowFrames; ++Frame)
	{
		for (int32 Bone = 0; Bone < NumBones; ++Bone)
		{
			const float* Values = Session->Output.GetData() + (Frame * NumBones + Bone) * 12;
			FMatrix Matrix = FMatrix::Identity;
			for (int32 Row = 0; Row < 3; ++Row)
			{
				for (int32 Column = 0; Column < 3; ++Column)
				{
					Matrix.M[Row][Column] = Values[3 + Column * 3 + Row];
				}
			}
			Component[Bone] = FTransform(FQuat(Matrix).GetNormalized(), FVector(Values[0], Values[1], Values[2]));
			if (Component[Bone].ContainsNaN())
			{
				return false;
			}
		}
		TArray<FTransform> Local;
		ToLocal(Component, Local);
		Window.Append(Local);
	}
	Playback->MergeWindow(LastSample - Session->WindowFrames + 1, Session->WindowFrames, NumBones, Window);
	return true;
}

void FAnimNode_AIAnimation::ToPositions(TConstArrayView<FTransform> Local, TArray<FVector>& Positions) const
{
	TArray<FTransform> Component;
	Component.SetNum(Local.Num());
	Positions.SetNum(Local.Num());
	for (int32 Bone = 0; Bone < Local.Num(); ++Bone)
	{
		const int32 Parent = Session->Bones[Bone].ParentIndex;
		Component[Bone] = Parent == INDEX_NONE ? Local[Bone] : Local[Bone] * Component[Parent];
		Positions[Bone] = Component[Bone].GetTranslation();
	}
}

void FAnimNode_AIAnimation::MeasureQuality(int64 Index)
{
	if (Index == LastQualityIndex)
	{
		return;
	}
	const FAIAnimationBufferedPose* Frame = Playback->Find(Index);
	if (!Frame || Frame->Weight <= 0.0)
	{
		return;
	}
	TArray<FVector> ModelPositions;
	TArray<FVector> SourcePositions;
	TArray<FTransform> CorrectedModel;
	bool bCorrectedReady = false;
	const TConstArrayView<int32> ActiveReferences = CVarAIAnimationHardReferences.GetValueOnAnyThread() != 0 ? TConstArrayView<int32>(HardReferenceFrames) : TConstArrayView<int32>();
	if (!Playback->Read(double(Index), false, 1.0, CorrectedModel, bCorrectedReady, ActiveReferences) || !bCorrectedReady)
	{
		return;
	}
	ToPositions(CorrectedModel, ModelPositions);
	ToPositions(Frame->Source, SourcePositions);
	double SquaredError = 0.0;
	double SquaredRotation = 0.0;
	double ModelAcceleration = 0.0;
	double SourceAcceleration = 0.0;
	double VelocityError = 0.0;
	const bool bAdjacent = Index == LastQualityIndex + 1 && PreviousModelPositions.Num() == ModelPositions.Num();
	Stats.bTemporalMetricValid = bAdjacent && OlderModelPositions.Num() == ModelPositions.Num();
	for (int32 Bone = 0; Bone < ModelPositions.Num(); ++Bone)
	{
		SquaredError += FVector::DistSquared(ModelPositions[Bone], SourcePositions[Bone]);
		SquaredRotation += FMath::Square(FMath::RadiansToDegrees(CorrectedModel[Bone].GetRotation().AngularDistance(Frame->Source[Bone].GetRotation())));
		if (Stats.bTemporalMetricValid)
		{
			ModelAcceleration += (ModelPositions[Bone] - 2.0 * PreviousModelPositions[Bone] + OlderModelPositions[Bone]).SizeSquared();
			SourceAcceleration += (SourcePositions[Bone] - 2.0 * PreviousSourcePositions[Bone] + OlderSourcePositions[Bone]).SizeSquared();
			VelocityError += ((ModelPositions[Bone] - PreviousModelPositions[Bone]) - (SourcePositions[Bone] - PreviousSourcePositions[Bone])).SizeSquared();
		}
	}
	const double Count = ModelPositions.Num();
	Stats.LastJointErrorCm = FMath::Sqrt(SquaredError / Count);
	Stats.LastQualityAssetFrame = Frame->AssetFrame;
	Stats.bLastQualityIsHardReference = ActiveReferences.Contains(Frame->AssetFrame);
	Stats.LastRotationErrorDegrees = FMath::Sqrt(SquaredRotation / Count);
	Stats.LastModelAcceleration = FMath::Sqrt(ModelAcceleration / Count);
	Stats.LastSourceAcceleration = FMath::Sqrt(SourceAcceleration / Count);
	Stats.LastVelocityError = FMath::Sqrt(VelocityError / Count);
	++Stats.NumQualitySamples;
	OlderModelPositions = bAdjacent ? MoveTemp(PreviousModelPositions) : TArray<FVector>();
	OlderSourcePositions = bAdjacent ? MoveTemp(PreviousSourcePositions) : TArray<FVector>();
	PreviousModelPositions = MoveTemp(ModelPositions);
	PreviousSourcePositions = MoveTemp(SourcePositions);
	LastQualityIndex = Index;
}

void FAnimNode_AIAnimation::GatherDebugData(FNodeDebugData& DebugData)
{
	DebugData.AddDebugItem(FString::Printf(TEXT("AIAnimation GPU %.2f ms | delay %d | inference %llu | error %.2f cm"), Stats.LastInferenceMs, Stats.DelayFrames, Stats.NumInferences, Stats.LastJointErrorCm));
	Source.GatherDebugData(DebugData);
}
