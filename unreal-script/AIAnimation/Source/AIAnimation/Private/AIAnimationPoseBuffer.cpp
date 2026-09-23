// Copyright ZhaoZining. All Rights Reserved.

// 同一时间点只融合尚未播放的预测；四元数采用最短弧插值，避免跨符号翻转。
#include "AIAnimationPoseBuffer.h"

namespace
{
	FTransform BlendPose(const FTransform& A, const FTransform& B, double Alpha)
	{
		return FTransform(FQuat::Slerp(A.GetRotation(), B.GetRotation(), Alpha).GetNormalized(), FMath::Lerp(A.GetTranslation(), B.GetTranslation(), Alpha), FMath::Lerp(A.GetScale3D(), B.GetScale3D(), Alpha));
	}
}

void FAIAnimationPoseBuffer::Reset()
{
	Frames.Reset();
	FrozenThrough = -1;
}

void FAIAnimationPoseBuffer::AddSource(int64 Index, TConstArrayView<FTransform> Pose, int32 AssetFrame, double AssetTimeSeconds, TConstArrayView<FTransform> FullSource)
{
	check(Frames.IsEmpty() || Frames.Last().Index + 1 == Index);
	FAIAnimationBufferedPose& Frame = Frames.AddDefaulted_GetRef();
	Frame.Index = Index;
	Frame.AssetFrame = AssetFrame;
	Frame.AssetTimeSeconds = AssetTimeSeconds;
	Frame.Source.Append(Pose.GetData(), Pose.Num());
	Frame.FullSource.Append(FullSource.GetData(), FullSource.Num());
	if (Frames.Num() > 1)
	{
		const FAIAnimationBufferedPose& Previous = Frames[Frames.Num() - 2];
		bool bStationary = Previous.Source.Num() == Pose.Num();
		for (int32 Bone = 0; bStationary && Bone < Pose.Num(); ++Bone)
		{
			bStationary = Pose[Bone].GetTranslation().Equals(Previous.Source[Bone].GetTranslation(), 0.01)
				&& Pose[Bone].GetRotation().AngularDistance(Previous.Source[Bone].GetRotation()) < 0.001;
		}
		Frame.StationarySamples = bStationary ? FMath::Min(Previous.StationarySamples + 1, 1000) : 0;
		Frame.ResumeSamples = !bStationary && Previous.StationarySamples >= 6 ? 4 : FMath::Max(0, Previous.ResumeSamples - 1);
	}
}

const FAIAnimationBufferedPose* FAIAnimationPoseBuffer::Find(int64 Index) const
{
	if (Frames.IsEmpty())
	{
		return nullptr;
	}
	const int64 Offset = Index - Frames[0].Index;
	return Offset >= 0 && Offset < Frames.Num() ? &Frames[int32(Offset)] : nullptr;
}

void FAIAnimationPoseBuffer::MergeWindow(int64 Start, int32 WindowFrames, int32 NumBones, TConstArrayView<FTransform> Poses)
{
	check(Poses.Num() == WindowFrames * NumBones);
	for (FAIAnimationBufferedPose& Frame : Frames)
	{
		const int64 Offset = Frame.Index - Start;
		if (Frame.Index <= FrozenThrough || Offset < 0 || Offset >= WindowFrames)
		{
			continue;
		}
		const double Weight = 1.0 + FMath::Min(Offset, WindowFrames - 1 - Offset);
		const double Alpha = Weight / (Frame.Weight + Weight);
		if (Frame.Model.IsEmpty())
		{
			Frame.Model.Append(Poses.GetData() + Offset * NumBones, NumBones);
		}
		else
		{
			for (int32 Bone = 0; Bone < NumBones; ++Bone)
			{
				Frame.Model[Bone] = BlendPose(Frame.Model[Bone], Poses[Offset * NumBones + Bone], Alpha);
			}
		}
		Frame.Weight += Weight;
	}
}

bool FAIAnimationPoseBuffer::Read(double Position, bool bSourceOnly, double ModelAlpha, TArray<FTransform>& OutPose, bool& bOutModelReady, TConstArrayView<int32> HardReferenceFrames) const
{
	const int64 Lower = FMath::FloorToInt64(Position);
	const int64 Upper = FMath::CeilToInt64(Position);
	const FAIAnimationBufferedPose* A = Find(Lower);
	const FAIAnimationBufferedPose* B = Find(Upper);
	// 并行动画求值偶尔比下一采样帧更早读取；保持最近已采样姿态，避免回退到当前源帧产生跳变。
	if (A && !B && Upper == Lower + 1)
	{
		B = A;
	}
	if (!A || !B)
	{
		bOutModelReady = false;
		return false;
	}
	bOutModelReady = A->Weight > 0.0 && B->Weight > 0.0;
	const auto CorrectModel = [this, HardReferenceFrames](const FAIAnimationBufferedPose& Frame, int32 Bone)
	{
		const FAIAnimationBufferedPose* Left = nullptr;
		const FAIAnimationBufferedPose* Right = nullptr;
		for (const FAIAnimationBufferedPose& Candidate : Frames)
		{
			if (Candidate.AssetFrame == INDEX_NONE || Candidate.Weight <= 0.0 || Candidate.Source.Num() <= Bone || Candidate.Model.Num() <= Bone)
			{
				continue;
			}
			bool bSelected = false;
			for (int32 ReferenceFrame : HardReferenceFrames)
			{
				bSelected |= ReferenceFrame == Candidate.AssetFrame;
			}
			if (!bSelected)
			{
				continue;
			}
			if (Candidate.Index <= Frame.Index && (!Left || Candidate.Index > Left->Index))
			{
				Left = &Candidate;
			}
			if (Candidate.Index >= Frame.Index && (!Right || Candidate.Index < Right->Index))
			{
				Right = &Candidate;
			}
		}
		if (Left == &Frame || Right == &Frame)
		{
			return Frame.Source[Bone];
		}
		const auto AnchorDelta = [Bone](const FAIAnimationBufferedPose& Anchor)
		{
			return FTransform((Anchor.Source[Bone].GetRotation() * Anchor.Model[Bone].GetRotation().Inverse()).GetNormalized(),
				Anchor.Source[Bone].GetTranslation() - Anchor.Model[Bone].GetTranslation());
		};
		FTransform Delta = FTransform::Identity;
		double Weight = 0.0;
		if (Left && Right && Right->Index - Left->Index <= 16)
		{
			const double Fraction = double(Frame.Index - Left->Index) / double(Right->Index - Left->Index);
			const FTransform L = AnchorDelta(*Left);
			const FTransform R = AnchorDelta(*Right);
			Delta = FTransform(FQuat::Slerp(L.GetRotation(), R.GetRotation(), Fraction).GetNormalized(), FMath::Lerp(L.GetTranslation(), R.GetTranslation(), Fraction));
			Weight = 1.0;
		}
		else
		{
			const FAIAnimationBufferedPose* Nearest = !Left ? Right : !Right ? Left : Frame.Index - Left->Index <= Right->Index - Frame.Index ? Left : Right;
			if (Nearest)
			{
				const double Distance = FMath::Abs(Frame.Index - Nearest->Index);
				const double T = FMath::Clamp(1.0 - Distance / 8.0, 0.0, 1.0);
				Weight = T * T * (3.0 - 2.0 * T);
				Delta = AnchorDelta(*Nearest);
			}
		}
		FTransform Corrected = Frame.Model[Bone];
		Corrected.SetTranslation(Corrected.GetTranslation() + Weight * Delta.GetTranslation());
		Corrected.SetRotation((FQuat::Slerp(FQuat::Identity, Delta.GetRotation(), Weight) * Corrected.GetRotation()).GetNormalized());
		return Corrected;
	};
	OutPose.SetNum(A->Source.Num());
	for (int32 Bone = 0; Bone < OutPose.Num(); ++Bone)
	{
		const FTransform Source = BlendPose(A->Source[Bone], B->Source[Bone], Position - Lower);
		OutPose[Bone] = Source;
		if (!bSourceOnly && bOutModelReady)
		{
			const FTransform Model = HardReferenceFrames.IsEmpty() ? BlendPose(A->Model[Bone], B->Model[Bone], Position - Lower)
				: BlendPose(CorrectModel(*A, Bone), CorrectModel(*B, Bone), Position - Lower);
			OutPose[Bone] = BlendPose(Source, Model, ModelAlpha);
		}
	}
	return true;
}

bool FAIAnimationPoseBuffer::ReadFullSource(double Position, TArray<FTransform>& OutPose) const
{
	const int64 Lower = FMath::FloorToInt64(Position);
	const FAIAnimationBufferedPose* A = Find(Lower);
	const FAIAnimationBufferedPose* B = Find(FMath::CeilToInt64(Position));
	if (A && !B)
	{
		B = A;
	}
	if (!A || !B || A->FullSource.IsEmpty() || A->FullSource.Num() != B->FullSource.Num())
	{
		return false;
	}
	OutPose.SetNum(A->FullSource.Num());
	for (int32 Bone = 0; Bone < OutPose.Num(); ++Bone)
	{
		OutPose[Bone] = BlendPose(A->FullSource[Bone], B->FullSource[Bone], Position - Lower);
	}
	return true;
}

void FAIAnimationPoseBuffer::StabilizeStationary(double Position)
{
	const int64 Upper = FMath::CeilToInt64(Position);
	for (int32 Offset = 1; Offset < Frames.Num(); ++Offset)
	{
		FAIAnimationBufferedPose& Frame = Frames[Offset];
		const FAIAnimationBufferedPose& Previous = Frames[Offset - 1];
		if (Frame.Index <= FrozenThrough || Frame.Index > Upper || Frame.Weight <= 0.0 || Previous.Weight <= 0.0)
		{
			continue;
		}
		if (Frame.StationarySamples >= 6)
		{
			Frame.Model = Previous.Model;
		}
		else if (Frame.ResumeSamples > 0)
		{
			for (int32 Bone = 0; Bone < Frame.Model.Num(); ++Bone)
			{
				Frame.Model[Bone] = BlendPose(Previous.Model[Bone], Frame.Model[Bone], (5.0 - Frame.ResumeSamples) / 4.0);
			}
		}
	}
}

void FAIAnimationPoseBuffer::Commit(double Position)
{
	if (!Frames.IsEmpty())
	{
		FrozenThrough = FMath::Max(FrozenThrough, FMath::Min(FMath::CeilToInt64(Position), Frames.Last().Index));
	}
	// 保留完整硬参考桥接区间，避免已播放的锚点在过渡完成前被移除。
	const int64 KeepFrom = FMath::FloorToInt64(Position) - 16;
	while (!Frames.IsEmpty() && Frames[0].Index < KeepFrom)
	{
		Frames.RemoveAt(0, 1, EAllowShrinking::No);
	}
}
