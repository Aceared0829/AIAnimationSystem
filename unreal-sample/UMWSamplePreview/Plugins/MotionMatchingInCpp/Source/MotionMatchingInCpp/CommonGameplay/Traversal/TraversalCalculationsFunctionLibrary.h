#pragma once

#include "CoreMinimal.h"
#include "Engine/HitResult.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "MotionMatchingInCpp/CommonGameplay/Player/Data/TraversalStructs.h"
#include "TraversalCalculationsFunctionLibrary.generated.h"

class UTraversalComponent;

/**
 * Traversal（攀爬/翻越）系统的核心计算函数库。
 * 基于物理追踪（LineTrace / PlaneTrace）检测物体边缘和可攀爬表面，
 * 支持倒置物体（通过 UpVector 符号翻转自动适配玩家方向）。
 */
UCLASS()
class MOTIONMATCHINGINCPP_API UTraversalCalculationsFunctionLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/** 顶层入口：基于初始命中结果检测并填充完整的攀爬数据到 TraversalCheckStruct */
	UFUNCTION(BlueprintCallable)
	static void TryAndCalculateLedges(UTraversalComponent* TraversalComponent,
	                           UPARAM(ref) FHitResult& InitialHitResult,
	                           UPARAM(ref) FTraversalCheckResult& TraversalCheckStruct);

	/**
	 * 核心算法：分析单个命中点，计算前/后侧边缘的位置和法线。
	 * @param HitResult        初始命中结果（会被微调）
	 * @param PlayerDirection  玩家朝向，即组件的上方向参考
	 * @param FoundFrontLedge  输出：是否找到前侧边缘
	 * @param StartLedgeLocation  输出：前侧边缘世界坐标
	 * @param StartLedgeNormal    输出：前侧边缘表面法线
	 * @param FoundBackLedge   输出：是否找到后侧边缘
	 * @param EndLedgeLocation  输出：后侧边缘世界坐标
	 * @param EndLedgeNormal    输出：后侧边缘表面法线
	 */
	UFUNCTION(BlueprintCallable)
	static void ComputeLedgeData(UTraversalComponent* TraversalComponent,UPARAM(ref) FHitResult& HitResult,
	                      FVector PlayerDirection, bool& FoundFrontLedge,
	                      FVector& StartLedgeLocation, FVector& StartLedgeNormal, bool& FoundBackLedge,
	                      FVector& EndLedgeLocation, FVector& EndLedgeNormal, FVector InitialHit, float TraceLength,
	                      FVector StartLedge, FVector EndLedge, FVector StartNormal, FVector EndNormal,
	                      bool HasBackLedge, FVector AbsoluteObjectUpVector, double RightEdgeDistance);

	/**
	 * 沿命中平面追踪：通过两次叉积构建沿表面旋转对齐的方向向量，
	 * 然后沿该方向进行线条追踪以检测表面边缘。
	 * 起点向平面内推 1 单位确保能命中表面边界，终点延展 1.5 倍防止漏检。
	 */
	UFUNCTION(BlueprintCallable)
	static bool TraceAlongHitPlane(UTraversalComponent* TraversalComponent, const FHitResult& Hit, float TraceLength,
	                        FVector TraceDirection, FHitResult& OutHit);

	/**
	 * 将命中点向物体包围盒原点微移 1 单位。
	 * 如果初始命中在物体边缘，后续追踪可能会穿透失败，此函数确保起点可靠。
	 */
	UFUNCTION(BlueprintCallable)
	static void NudgeTraceTowardsObjectOrigin(UTraversalComponent* TraversalComponent,UPARAM(ref) FHitResult& HitResult);

	/** 将命中结果的 ImpactPoint 替换为指定坐标 */
	UFUNCTION(BlueprintCallable)
	static  void SetTraceHitPoint(UTraversalComponent* TraversalComponent,UPARAM(ref) FHitResult& HitResult,
	                      FVector NewImpactPoint);

	/**
	 * 检测命中点是否靠近物体角落，并计算偏移后的角落点。
	 * 当靠近角落时，将命中点向角落反方向偏移半个 LedgeWidth，防止抓取空气。
	 */
	UFUNCTION(BlueprintCallable)
	static void TraceCorners(UTraversalComponent* TraversalComponent, const FHitResult& Hit, FVector TraceDirection,
	                  float TraceLength, FVector& OffsettedCornerPoint,
	                  bool& CloseToCorner, double& DistanceToCorner);

	/**
	 * 在命中的组件上进行宽度方向的双向追踪。
	 * 以 ImpactPoint 为中心，向 Direction 方向偏移半个 MinLedgeWidth，同时沿法线方向
	 * 延伸 MinFrontLedgeDepth 构成起始/结束点，检查表面在此宽度范围内是否连续。
	 */
	UFUNCTION(BlueprintCallable)
	static bool TraceWidth(UTraversalComponent* TraversalComponent, const FHitResult& Hit, FVector Direction);

};
