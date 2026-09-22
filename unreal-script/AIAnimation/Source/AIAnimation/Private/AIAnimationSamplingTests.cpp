// Copyright ZhaoZining. All Rights Reserved.

// 回归验证跨渲染帧率的固定采样时间，以及不能掩盖缺样本或回退的验收条件。
#include "AIAnimationSampling.h"
#include "AIAnimationPoseBuffer.h"
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAIAnimationSamplingTest, "AIAnimation.Lab.FixedSampling", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FAIAnimationSamplingTest::RunTest(const FString& Parameters)
{
	for (int32 RenderRate : { 20, 45, 60, 144 })
	{
		double Remainder = 0.0;
		int32 Samples = 0;
		for (int32 Frame = 0; Frame < RenderRate * 2; ++Frame)
		{
			TArray<double> Fractions;
			AIAnimationSampling::Advance(1.0 / RenderRate, 30.0, Remainder, Fractions);
			for (double Fraction : Fractions)
			{
				++Samples;
				const double SampleTime = (Frame + Fraction) / RenderRate;
				TestEqual(TEXT("采样时间必须落在 30 Hz 网格上"), SampleTime, Samples / 30.0, 1.e-7);
			}
		}
		TestEqual(TEXT("两秒内补齐 60 个采样点"), Samples, 60);
	}
	TestFalse(TEXT("动作没有样本不能通过"), AIAnimationSampling::Passed(0, 0, 0, 0));
	TestFalse(TEXT("存在静默回退不能通过"), AIAnimationSampling::Passed(100, 0, 1, 0));
	TestFalse(TEXT("存在推理失败不能通过"), AIAnimationSampling::Passed(100, 1, 0, 0));
	TestFalse(TEXT("存在游戏线程跳过不能通过"), AIAnimationSampling::Passed(100, 0, 0, 1));
	TestTrue(TEXT("每动作有效样本达到门槛且无异常"), AIAnimationSampling::Passed(20, 0, 0, 0));
	return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAIAnimationPlaybackTest, "AIAnimation.Lab.PlaybackBuffer", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FAIAnimationPlaybackTest::RunTest(const FString& Parameters)
{
	FAIAnimationPoseBuffer Buffer;
	TArray<FTransform> Window;
	for (int32 Index = 0; Index < 16; ++Index)
	{
		TArray<FTransform> Source = { FTransform(FVector(Index, 0, 0)) };
		Buffer.AddSource(Index, Source);
		Window.Add(FTransform(FVector(Index + 10, 0, 0)));
	}
	Buffer.MergeWindow(0, 16, 1, Window);
	TArray<FTransform> Pose;
	bool bReady = false;
	TestTrue(TEXT("连续时间点可读"), Buffer.Read(5.5, false, 1.0, Pose, bReady));
	TestTrue(TEXT("两端均有模型输出"), bReady);
	TestEqual(TEXT("模型输出按时间插值"), Pose[0].GetTranslation().X, 15.5, 1.e-6);
	Buffer.Read(5.5, true, 1.0, Pose, bReady);
	TestEqual(TEXT("参考角色读取同一时间点"), Pose[0].GetTranslation().X, 5.5, 1.e-6);
	Buffer.Commit(5.5);
	for (int32 Index = 16; Index < 20; ++Index)
	{
		TArray<FTransform> Source = { FTransform(FVector(Index, 0, 0)) };
		Buffer.AddSource(Index, Source);
	}
	Window.Reset();
	for (int32 Index = 4; Index < 20; ++Index)
	{
		Window.Add(FTransform(FQuat(0, 0, 0, -1), FVector(Index + 30, 0, 0)));
	}
	Buffer.MergeWindow(4, 16, 1, Window);
	Buffer.Read(5.6, false, 1.0, Pose, bReady);
	TestEqual(TEXT("迟到窗口不能改写已使用的插值端点"), Pose[0].GetTranslation().X, 15.6, 1.e-6);
	TestTrue(TEXT("未播放区域仍参与融合"), Buffer.Find(7)->Model[0].GetTranslation().X > 17.0);
	TestEqual(TEXT("四元数符号相反不产生翻转"), Buffer.Find(7)->Model[0].GetRotation().AngularDistance(FQuat::Identity), 0.0, 1.e-6);
	for (int32 Index = 20; Index < 2000; ++Index)
	{
		TArray<FTransform> Source = { FTransform(FVector(Index, 0, 0)) };
		Buffer.AddSource(Index, Source);
		Buffer.Commit(Index - 8.0);
	}
	TestTrue(TEXT("长时播放缓冲保持有界"), Buffer.Num() <= 12);
	Buffer.Reset();
	TestNull(TEXT("回绕清除上一段模型姿态"), Buffer.Find(0));
	TArray<FTransform> NewSource = { FTransform(FVector(100, 0, 0)) };
	Buffer.AddSource(0, NewSource);
	Buffer.Read(0.0, false, 1.0, Pose, bReady);
	TestFalse(TEXT("新段没有继承旧模型状态"), bReady);
	TestEqual(TEXT("重新预热时返回新源姿态"), Pose[0].GetTranslation().X, 100.0, 1.e-6);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAIAnimationStationaryTest, "AIAnimation.Lab.StationaryPlayback", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FAIAnimationStationaryTest::RunTest(const FString& Parameters)
{
	FAIAnimationPoseBuffer Buffer;
	TArray<FTransform> Window;
	for (int32 Index = 0; Index < 16; ++Index)
	{
		TArray<FTransform> Source = { FTransform::Identity };
		Buffer.AddSource(Index, Source);
		Window.Add(FTransform(FVector(Index, 0, 0)));
	}
	Buffer.MergeWindow(0, 16, 1, Window);
	for (int32 Index = 0; Index < 16; ++Index)
	{
		Buffer.StabilizeStationary(Index);
		Buffer.Commit(Index);
	}
	TestEqual(TEXT("静止源姿态不继承解码窗口的周期性漂移"), Buffer.Find(15)->Model[0].GetTranslation().X, 5.0, 1.e-6);
	TArray<FTransform> Moving = { FTransform(FVector(10, 0, 0)) };
	Buffer.AddSource(16, Moving);
	for (FTransform& Pose : Window)
	{
		Pose.SetTranslation(FVector(100, 0, 0));
	}
	Buffer.MergeWindow(1, 16, 1, Window);
	Buffer.StabilizeStationary(16.0);
	const double ResumedPosition = Buffer.Find(16)->Model[0].GetTranslation().X;
	TestTrue(TEXT("源动作恢复后解除静止锁定"), ResumedPosition > 5.0);
	TestTrue(TEXT("解除锁定时保留短过渡"), ResumedPosition < 100.0);
	return true;
}
#endif
