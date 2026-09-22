// Copyright ZhaoZining. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"

/** 固定时间网格；调用方保存前后姿态，并负责在断点和超过 0.25 秒的间隔处重置。 */
namespace AIAnimationSampling
{
	/** 输出本段内采样点的插值比例，覆盖 OutFractions；RemainderSeconds 保存上个采样点后的余量。 */
	inline void Advance(double DeltaSeconds, double SampleRate, double& RemainderSeconds, TArray<double>& OutFractions)
	{
		OutFractions.Reset();
		if (DeltaSeconds <= 0.0)
		{
			return;
		}
		const double Period = 1.0 / SampleRate;
		for (double Offset = Period - RemainderSeconds; Offset <= DeltaSeconds + 1.e-8; Offset += Period)
		{
			OutFractions.Add(FMath::Clamp(Offset / DeltaSeconds, 0.0, 1.0));
		}
		RemainderSeconds = FMath::Max(0.0, RemainderSeconds + DeltaSeconds - OutFractions.Num() * Period);
	}

	/** 每个动作独立满足门槛；失败、静默回退和游戏线程跳过均不得判通过。 */
	inline bool Passed(int32 Samples, uint64 Failures, uint64 Fallbacks, uint64 GameThreadSkips)
	{
		return Samples >= 20 && Failures == 0 && Fallbacks == 0 && GameThreadSkips == 0;
	}
}
