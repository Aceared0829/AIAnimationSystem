// Copyright ZhaoZining. All Rights Reserved.

#include "AIAnimationPreviewCache.h"
#include "HAL/FileManager.h"
#include "Misc/AutomationTest.h"
#include "Misc/Crc.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/BufferArchive.h"
#include "Serialization/MemoryReader.h"

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAIAnimationCacheTest, "AIAnimation.Lab.PreviewCache", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FAIAnimationCacheTest::RunTest(const FString& Parameters)
{
	const FString Animation = TEXT("/Automation/AIAnimation/") + FGuid::NewGuid().ToString();
	const FString Path = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("AIAnimationPreview"), FString::Printf(TEXT("Latest_%08X.bin"), FCrc::StrCrc32(*Animation)));
	FAIAnimationPreviewCache Cache;
	Cache.Reset(TEXT("测试缓存"));
	for (int32 Index = 0; Index < 2; ++Index)
	{
		FAIAnimationCachedFrame& Frame = Cache.Frames.AddDefaulted_GetRef();
		Frame.SourceTimeSeconds = Index / 30.0f;
		for (int32 Lane = 0; Lane < 3; ++Lane)
		{
			Frame.BoneComponent[Lane].Add(FTransform(FVector(Index, Lane, 0)));
		}
	}
	TestTrue(TEXT("有效缓存写入"), Cache.Save(Animation));
	FAIAnimationPreviewCache Loaded;
	TestTrue(TEXT("有效缓存读取"), Loaded.Load(Animation, Cache.Key, 1));
	TestEqual(TEXT("完整读回所有帧"), Loaded.Frames.Num(), 2);
	TestFalse(TEXT("骨骼数量不匹配拒绝"), Loaded.Load(Animation, Cache.Key, 2));
	TestFalse(TEXT("过期配置拒绝"), Loaded.Load(Animation, TEXT("stale"), 1));
	TArray<uint8> Bytes;
	FFileHelper::LoadFileToArray(Bytes, *Path);
	const TArray<uint8> ValidBytes = Bytes;
	int32 HugeCount = MAX_int32;
	FMemory::Memcpy(Bytes.GetData() + 8, &HugeCount, sizeof(HugeCount));
	FFileHelper::SaveArrayToFile(Bytes, *Path);
	TestFalse(TEXT("损坏字符串长度在分配前拒绝"), Loaded.Load(Animation, Cache.Key, 1));
	Bytes = ValidBytes;
	FMemoryReader Reader(Bytes, true);
	uint32 Magic = 0;
	uint32 Version = 0;
	FString Key;
	int32 Count = 0;
	float Time = 0;
	Reader << Magic << Version << Key << Count << Time;
	FMemory::Memcpy(Bytes.GetData() + Reader.Tell(), &HugeCount, sizeof(HugeCount));
	FFileHelper::SaveArrayToFile(Bytes, *Path);
	TestFalse(TEXT("损坏骨骼长度在分配前拒绝"), Loaded.Load(Animation, Cache.Key, 1));
	Bytes = ValidBytes;
	Bytes.SetNum(Bytes.Num() - 1);
	FFileHelper::SaveArrayToFile(Bytes, *Path);
	TestFalse(TEXT("截断文件拒绝"), Loaded.Load(Animation, Cache.Key, 1));
	TestEqual(TEXT("读取失败不覆盖上一份完整缓存"), Loaded.Frames.Num(), 2);
	Cache.Frames[1].SourceTimeSeconds = 0;
	TestFalse(TEXT("时间倒退不写入"), Cache.Save(Animation));
	IFileManager::Get().Delete(*Path);
	return true;
}
#endif
