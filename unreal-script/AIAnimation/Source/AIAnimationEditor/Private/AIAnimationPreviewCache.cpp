// Copyright ZhaoZining. All Rights Reserved.

#include "AIAnimationPreviewCache.h"
#include "HAL/FileManager.h"
#include "Misc/Crc.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/BufferArchive.h"
#include "Serialization/MemoryReader.h"

namespace
{
	constexpr uint32 CacheMagic = 0x41495043;
	constexpr uint32 CacheVersion = 2;
	constexpr int32 MaxCacheFrames = 12000;
	constexpr int32 MaxCacheBones = 4096;
	constexpr int32 MaxCacheKeyChars = 16384;
	constexpr int64 MaxCacheFileBytes = 512ll * 1024 * 1024;
}

void FAIAnimationCachedFrame::Serialize(FArchive& Archive)
{
	Archive << SourceTimeSeconds;
	for (TArray<FTransform>& Pose : BoneComponent)
	{
		int32 BoneCount = Pose.Num();
		Archive << BoneCount;
		if (Archive.IsError() || BoneCount < 1 || BoneCount > MaxCacheBones
			|| (Archive.IsLoading() && int64(BoneCount) * 40 > Archive.TotalSize() - Archive.Tell()))
		{
			Archive.SetError();
			return;
		}
		if (Archive.IsLoading())
		{
			Pose.SetNum(BoneCount);
		}
		for (FTransform& Bone : Pose)
		{
			Archive << Bone;
		}
	}
	Archive << InferenceMs << JointErrorCm << NumInferences << NumQualitySamples;
}

void FAIAnimationPreviewCache::Reset(const FString& InKey)
{
	Key = InKey;
	Frames.Reset();
}

FString FAIAnimationPreviewCache::CachePath(const FString& AnimationPath)
{
	return FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("AIAnimationPreview"),
		FString::Printf(TEXT("Latest_%08X.bin"), FCrc::StrCrc32(*AnimationPath)));
}

bool FAIAnimationPreviewCache::Load(const FString& AnimationPath, const FString& ExpectedKey, int32 ExpectedBoneCount)
{
	if (ExpectedBoneCount <= 0 || ExpectedBoneCount > MaxCacheBones)
	{
		return false;
	}
	const FString Path = CachePath(AnimationPath);
	const int64 FileSize = IFileManager::Get().FileSize(*Path);
	if (FileSize <= 0 || FileSize > MaxCacheFileBytes)
	{
		return false;
	}
	TArray<uint8> Bytes;
	if (!FFileHelper::LoadFileToArray(Bytes, *Path))
	{
		return false;
	}
	FMemoryReader Reader(Bytes, true);
	uint32 Magic = 0;
	uint32 Version = 0;
	FString StoredKey;
	int32 Count = 0;
	Reader << Magic << Version;
	const int64 KeyOffset = Reader.Tell();
	int32 KeyChars = 0;
	Reader << KeyChars;
	const int64 AbsoluteChars = FMath::Abs(int64(KeyChars));
	const int64 KeyBytes = AbsoluteChars * (KeyChars < 0 ? 2 : 1);
	if (Reader.IsError() || AbsoluteChars > MaxCacheKeyChars || KeyBytes > Reader.TotalSize() - Reader.Tell())
	{
		return false;
	}
	Reader.Seek(KeyOffset);
	Reader << StoredKey << Count;
	if (Reader.IsError() || Magic != CacheMagic || Version != CacheVersion || StoredKey != ExpectedKey || Count < 1 || Count > MaxCacheFrames
		|| int64(Count) * 3 * ExpectedBoneCount * sizeof(FTransform) > MaxCacheFileBytes
		|| int64(Count) * (3 * (4 + int64(ExpectedBoneCount) * 40) + 36) > Reader.TotalSize() - Reader.Tell())
	{
		return false;
	}
	TArray<FAIAnimationCachedFrame> LoadedFrames;
	LoadedFrames.SetNum(Count);
	for (int32 Index = 0; Index < LoadedFrames.Num(); ++Index)
	{
		FAIAnimationCachedFrame& Frame = LoadedFrames[Index];
		Frame.Serialize(Reader);
		if (Reader.IsError())
		{
			return false;
		}
		if (!FMath::IsFinite(Frame.SourceTimeSeconds) || (Index > 0 && Frame.SourceTimeSeconds <= LoadedFrames[Index - 1].SourceTimeSeconds))
		{
			return false;
		}
		for (const TArray<FTransform>& Pose : Frame.BoneComponent)
		{
			if (Pose.Num() != ExpectedBoneCount || Pose.ContainsByPredicate([](const FTransform& Bone) { return !Bone.IsValid(); }))
			{
				return false;
			}
		}
	}
	if (Reader.Tell() != Reader.TotalSize())
	{
		return false;
	}
	Key = MoveTemp(StoredKey);
	Frames = MoveTemp(LoadedFrames);
	return true;
}

bool FAIAnimationPreviewCache::Save(const FString& AnimationPath) const
{
	if (Frames.IsEmpty() || Frames.Num() > MaxCacheFrames || Key.Len() >= MaxCacheKeyChars)
	{
		return false;
	}
	const int32 BoneCount = Frames[0].BoneComponent[0].Num();
	if (BoneCount < 1 || BoneCount > MaxCacheBones || int64(Frames.Num()) * 3 * BoneCount * sizeof(FTransform) > MaxCacheFileBytes)
	{
		return false;
	}
	for (int32 Index = 0; Index < Frames.Num(); ++Index)
	{
		const FAIAnimationCachedFrame& Frame = Frames[Index];
		if (!FMath::IsFinite(Frame.SourceTimeSeconds) || (Index > 0 && Frame.SourceTimeSeconds <= Frames[Index - 1].SourceTimeSeconds))
		{
			return false;
		}
		for (const TArray<FTransform>& Pose : Frame.BoneComponent)
		{
			if (Pose.Num() != BoneCount || Pose.ContainsByPredicate([](const FTransform& Bone) { return !Bone.IsValid(); }))
			{
				return false;
			}
		}
	}
	FBufferArchive Writer;
	uint32 Magic = CacheMagic;
	uint32 Version = CacheVersion;
	FString StoredKey = Key;
	int32 Count = Frames.Num();
	Writer << Magic << Version << StoredKey << Count;
	for (const FAIAnimationCachedFrame& Frame : Frames)
	{
		FAIAnimationCachedFrame Copy = Frame;
		Copy.Serialize(Writer);
	}
	if (Writer.IsError() || Writer.Num() > MaxCacheFileBytes)
	{
		return false;
	}
	const FString Path = CachePath(AnimationPath);
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(Path), true);
	const FString PendingPath = Path + TEXT(".pending");
	if (!FFileHelper::SaveArrayToFile(Writer, *PendingPath))
	{
		return false;
	}
	return IFileManager::Get().Move(*Path, *PendingPath, true, true);
}
