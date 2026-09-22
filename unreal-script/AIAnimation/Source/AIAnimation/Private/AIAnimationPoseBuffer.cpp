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

void FAIAnimationPoseBuffer::AddSource(int64 Index, TConstArrayView<FTransform> Pose)
{
	check(Frames.IsEmpty() || Frames.Last().Index + 1 == Index);
	FAIAnimationBufferedPose& Frame = Frames.AddDefaulted_GetRef();
	Frame.Index = Index;
	Frame.Source.Append(Pose.GetData(), Pose.Num());
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

bool FAIAnimationPoseBuffer::Read(double Position, bool bSourceOnly, double ModelAlpha, TArray<FTransform>& OutPose, bool& bOutModelReady) const
{
	const int64 Lower = FMath::FloorToInt64(Position);
	const int64 Upper = FMath::CeilToInt64(Position);
	const FAIAnimationBufferedPose* A = Find(Lower);
	const FAIAnimationBufferedPose* B = Find(Upper);
	if (!A || !B)
	{
		bOutModelReady = false;
		return false;
	}
	bOutModelReady = A->Weight > 0.0 && B->Weight > 0.0;
	OutPose.SetNum(A->Source.Num());
	for (int32 Bone = 0; Bone < OutPose.Num(); ++Bone)
	{
		const FTransform Source = BlendPose(A->Source[Bone], B->Source[Bone], Position - Lower);
		OutPose[Bone] = Source;
		if (!bSourceOnly && bOutModelReady)
		{
			const FTransform Model = BlendPose(A->Model[Bone], B->Model[Bone], Position - Lower);
			OutPose[Bone] = BlendPose(Source, Model, ModelAlpha);
		}
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
	FrozenThrough = FMath::Max(FrozenThrough, FMath::CeilToInt64(Position));
	const int64 KeepFrom = FMath::FloorToInt64(Position) - 2;
	while (!Frames.IsEmpty() && Frames[0].Index < KeepFrom)
	{
		Frames.RemoveAt(0, 1, EAllowShrinking::No);
	}
}
