#include "TraversalCalculationsFunctionLibrary.h"

#include "Kismet/KismetMathLibrary.h"
#include "Kismet/KismetSystemLibrary.h"
#include "TraversalComponent.h"

// ─────────────────────────────────────────────────────────────────────────────
//  TryAndCalculateLedges
//  顶层入口：获取 Owner 的前向向量作为 PlayerDirection，调用 ComputeLedgeData
//  将结果填充到 FTraversalCheckResult 结构体中。
// ─────────────────────────────────────────────────────────────────────────────
void UTraversalCalculationsFunctionLibrary::TryAndCalculateLedges(UTraversalComponent* TraversalComponent,
                                                                  FHitResult& InitialHitResult, FTraversalCheckResult& TraversalCheckStruct)
{
	AActor* Owner = TraversalComponent->GetOwner();
	const FVector PlayerDirection = Owner ? Owner->GetActorForwardVector() : FVector::ZeroVector;

	bool bFoundFrontLedge = false;
	FVector StartLedgeLocation = FVector::ZeroVector;
	FVector StartLedgeNormal = FVector::ZeroVector;
	bool bFoundBackLedge = false;
	FVector EndLedgeLocation = FVector::ZeroVector;
	FVector EndLedgeNormal = FVector::ZeroVector;

	ComputeLedgeData(TraversalComponent, InitialHitResult, PlayerDirection,
	                 bFoundFrontLedge, StartLedgeLocation, StartLedgeNormal,
	                 bFoundBackLedge, EndLedgeLocation, EndLedgeNormal,
	                 FVector::ZeroVector, TraversalComponent->MinLedgeWidth,
	                 FVector::ZeroVector, FVector::ZeroVector,
	                 FVector::ZeroVector, FVector::ZeroVector,
	                 false, FVector::ZeroVector, 0.0);

	TraversalCheckStruct.bHasFrontLedge = bFoundFrontLedge;
	TraversalCheckStruct.FrontLedgeLocation = StartLedgeLocation;
	TraversalCheckStruct.FrontLedgeNormal = StartLedgeNormal;
	TraversalCheckStruct.bHasBackLedge = bFoundBackLedge;
	TraversalCheckStruct.BackLedgeLocation = EndLedgeLocation;
	TraversalCheckStruct.BackLedgeNormal = EndLedgeNormal;
	TraversalCheckStruct.HitComponent = InitialHitResult.Component.Get();
}

// ─────────────────────────────────────────────────────────────────────────────
//  ComputeLedgeData
//  核心边缘检测算法，执行顺序：
//    1. NudgeTraceTowardsObjectOrigin — 防止命中在物体边缘
//    2. 计算 TraceLength（包围球半径 × 2）和 TraceDirection（智能上方向）
//    3. TraceCorners — 角落检测，若靠近角落则微调命中点
//    4. TraceAlongHitPlane — 沿表面追踪找前侧边缘
//    5. 反向追踪 + 二次 TraceAlongHitPlane — 找后侧边缘穿透点
// ─────────────────────────────────────────────────────────────────────────────
void UTraversalCalculationsFunctionLibrary::ComputeLedgeData(UTraversalComponent* TraversalComponent,
	FHitResult& HitResult, FVector PlayerDirection, bool& FoundFrontLedge, FVector& StartLedgeLocation,
	FVector& StartLedgeNormal, bool& FoundBackLedge, FVector& EndLedgeLocation, FVector& EndLedgeNormal,
	FVector InitialHit, float TraceLength, FVector StartLedge, FVector EndLedge, FVector StartNormal, FVector EndNormal,
	bool HasBackLedge, FVector AbsoluteObjectUpVector, double RightEdgeDistance)
{
	// 1. 微移命中点，防止在物体边缘导致后续追踪穿透失败
	NudgeTraceTowardsObjectOrigin(TraversalComponent, HitResult);

	UPrimitiveComponent* HitComponent = HitResult.Component.Get();
	if (!HitComponent)
	{
		FoundFrontLedge = false;
		StartLedgeLocation = FVector::ZeroVector;
		StartLedgeNormal = FVector::ZeroVector;
		FoundBackLedge = false;
		EndLedgeLocation = FVector::ZeroVector;
		EndLedgeNormal = FVector::ZeroVector;
		return;
	}

	// 缓存初始 ImpactNormal（后续角落检测不会修改它）
	const FVector HitImpactNormal = HitResult.ImpactNormal;

	// 2. 计算实际追踪长度 = 物体包围球半径 × 2
	//    注释："Having a trace length of twice the radius means we can't have a trace
	//           which is too short, so long as our start is inside the sphere bounds"
	FVector Origin;
	FVector BoxExtent;
	float SphereRadius;
	UKismetSystemLibrary::GetComponentBounds(HitComponent, Origin, BoxExtent, SphereRadius);
	const float CalcTraceLength = SphereRadius * 2.0f;

	// 3. 智能上方向：GetUpVector() × Sign(Dot(Up, ActorUp))
	//    注释："To make sure we can mantle objects that are upside down,
	//           we make sure the up vector always points to the player's UP"
	//    当物体倒置时，点积为负，符号翻转使方向始终朝向玩家上方
	const FVector ComponentUp = HitComponent->GetUpVector();
	AActor* Owner = TraversalComponent->GetOwner();
	const FVector ActorUp = Owner ? Owner->GetActorUpVector() : FVector::UpVector;
	const float UpSign = FMath::Sign(FVector::DotProduct(ComponentUp, ActorUp));
	const FVector TraceDirection = ComponentUp * UpSign;

	// 4. 角落检测（两次，方向互为 Cross 反序以覆盖两个方向）：
	//    注释："Offset the trace towards the opposite direction of corners,
	//           by the half ledge width, ensuring we aren't grabbing the air
	//           if we are close to a corner"
	//    4a. Cross(ImpactNormal, TraceDirection) → 右侧角落检测
	const FVector CornerTraceDirA = FVector::CrossProduct(HitImpactNormal, TraceDirection);
	FVector CornerPoint;
	bool bCloseToCorner;
	double CornerDistance;
	TraceCorners(TraversalComponent, HitResult, CornerTraceDirA, CalcTraceLength,
	             CornerPoint, bCloseToCorner, CornerDistance);
	const double RightDistance = CornerDistance;

	if (bCloseToCorner)
	{
		SetTraceHitPoint(TraversalComponent, HitResult, CornerPoint);
	}

	//    4b. Cross(TraceDirection, ImpactNormal) → 左侧角落检测（反序）
	const FVector CornerTraceDirB = FVector::CrossProduct(TraceDirection, HitImpactNormal);
	TraceCorners(TraversalComponent, HitResult, CornerTraceDirB, CalcTraceLength,
	             CornerPoint, bCloseToCorner, CornerDistance);

	// 5. 宽度验证 + 角落偏移（无条件执行，对应蓝图 ExecutionSequence_2）：
	//    DistanceToCorner + RightDistance < MinLedgeWidth → 距两侧边缘过近，需宽度验证
	//    若验证不通过（表面在本侧宽度方向不连续）→ 提前返回默认值
	if ((CornerDistance + RightDistance) < TraversalComponent->MinLedgeWidth)
	{
		const FVector WidthDir = FVector::CrossProduct(TraceDirection, HitImpactNormal);
		if (!TraceWidth(TraversalComponent, HitResult, WidthDir))
		{
			FoundFrontLedge = false;
			StartLedgeLocation = FVector::ZeroVector;
			StartLedgeNormal = FVector::ZeroVector;
			FoundBackLedge = false;
			EndLedgeLocation = FVector::ZeroVector;
			EndLedgeNormal = FVector::ZeroVector;
			return;
		}
		if (!TraceWidth(TraversalComponent, HitResult, -WidthDir))
		{
			FoundFrontLedge = false;
			StartLedgeLocation = FVector::ZeroVector;
			StartLedgeNormal = FVector::ZeroVector;
			FoundBackLedge = false;
			EndLedgeLocation = FVector::ZeroVector;
			EndLedgeNormal = FVector::ZeroVector;
			return;
		}
	}
	else if (bCloseToCorner)
	{
		SetTraceHitPoint(TraversalComponent, HitResult, CornerPoint);
	}

	// 6. TraceAlongHitPlane → 沿表面追踪找前侧边缘
	//    Comment: "2. Given our initial hit, check for an edge by tracing towards the hit point, along the plane"
	FHitResult FrontHit;
	const bool bFrontHit = TraceAlongHitPlane(TraversalComponent, HitResult, CalcTraceLength, TraceDirection, FrontHit);

	if (!bFrontHit)
	{
		FoundFrontLedge = false;
		StartLedgeLocation = FVector::ZeroVector;
		StartLedgeNormal = FVector::ZeroVector;
		FoundBackLedge = false;
		EndLedgeLocation = FVector::ZeroVector;
		EndLedgeNormal = FVector::ZeroVector;
		return;
	}

	FoundFrontLedge = true;
	StartLedgeLocation = FrontHit.ImpactPoint;
	StartLedgeNormal = HitImpactNormal;

	// 7. 反向追踪：沿法线回溯，碰撞到背面穿透点后再次 TraceAlongHitPlane 找后侧边缘
	//    Comment: "3. Reverse our trace to figure out the penetrating point of the backface"
	//    Comment: "If we've found a hit from our backface trace, try to find the ledge
	//              by tracing along the hit plane from above"
	const FVector ReverseTraceStart = HitResult.ImpactPoint - HitResult.ImpactNormal * CalcTraceLength;

	FVector ReverseHitLocation;
	FVector ReverseHitNormal;
	FName ReverseBoneName;
	FHitResult BackHit;

	FoundBackLedge = HitComponent->K2_LineTraceComponent(ReverseTraceStart, HitResult.ImpactPoint,
	                                                     TraversalComponent->bTraceComplex,
	                                                     TraversalComponent->bShowTrace,
	                                                     TraversalComponent->bPersistentShowTrace,
	                                                     ReverseHitLocation, ReverseHitNormal, ReverseBoneName, BackHit);

	if (FoundBackLedge)
	{
		EndLedgeNormal = ReverseHitNormal;

		// 二次 TraceAlongHitPlane：在背面命中的表面上再次追踪，找到后侧边缘精确位置
		FHitResult SecondHit;
		if (TraceAlongHitPlane(TraversalComponent, BackHit, CalcTraceLength, TraceDirection, SecondHit))
		{
			EndLedgeLocation = SecondHit.ImpactPoint;
		}
	}
}

// ─────────────────────────────────────────────────────────────────────────────
//  TraceAlongHitPlane
//  沿命中表面进行边缘追踪：
//    Cross(ImpactNormal, TraceDirection) → 右向量（与物体旋转对齐）
//    Cross(RightVector, ImpactNormal)     → 沿表面的上方向
//    起点 = ImpactPoint - ImpactNormal（向平面内推 1 单位）
//    终点 = Lerp(起点, StartPoint, 1.5)（延伸超出原始命中点）
// ─────────────────────────────────────────────────────────────────────────────
bool UTraversalCalculationsFunctionLibrary::TraceAlongHitPlane(UTraversalComponent* TraversalComponent,
	const FHitResult& Hit, float TraceLength, FVector TraceDirection, FHitResult& OutHit)
{
	UPrimitiveComponent* HitComponent = Hit.Component.Get();
	if (!HitComponent)
	{
		return false;
	}

	const FVector ImpactPoint = Hit.ImpactPoint;
	const FVector ImpactNormal = Hit.ImpactNormal;

	// Cross( surface normal, component up vector ) → right vector aligned with object rotation
	const FVector RightVector = FVector::CrossProduct(ImpactNormal, TraceDirection);
	// Cross( right vector, surface normal ) → up vector pointing along the surface
	const FVector UpAlongSurface = FVector::CrossProduct(RightVector, ImpactNormal);
	const FVector NormalizedUp = UpAlongSurface.GetSafeNormal(UE_SMALL_NUMBER);

	// Push start point 1 unit into the plane so the trace can hit the surface edge
	const FVector StartPoint = ImpactPoint - ImpactNormal;
	// Extend along surface by TraceLength
	const FVector TraceStart = StartPoint + NormalizedUp * TraceLength;
	// VLerp with Alpha=1.5 extends the end beyond the original impact point
	const FVector TraceEnd = FMath::Lerp(TraceStart, StartPoint, 1.5f);

	FVector HitLocation;
	FVector HitNormal;
	FName BoneName;

	return HitComponent->K2_LineTraceComponent(TraceStart, TraceEnd, TraversalComponent->bTraceComplex,
	                                           TraversalComponent->bShowTrace,
	                                           TraversalComponent->bPersistentShowTrace, HitLocation, HitNormal,
	                                           BoneName, OutHit);
}

// ─────────────────────────────────────────────────────────────────────────────
//  NudgeTraceTowardsObjectOrigin
//  将命中点向物体包围盒原点微移 1 单位：
//    - GetComponentBounds 获取物体原点
//    - 将原点投影到命中平面
//    - 沿投影原点→命中点方向缩进 1 单位
// ─────────────────────────────────────────────────────────────────────────────
void UTraversalCalculationsFunctionLibrary::NudgeTraceTowardsObjectOrigin(UTraversalComponent* TraversalComponent,
	FHitResult& HitResult)
{
	USceneComponent* HitComponent = HitResult.Component.Get();
	if (!HitComponent)
	{
		return;
	}

	FVector Origin;
	FVector BoxExtent;
	float SphereRadius;
	UKismetSystemLibrary::GetComponentBounds(HitComponent, Origin, BoxExtent, SphereRadius);

	const FVector ProjectedOrigin = UKismetMathLibrary::ProjectPointOnToPlane(
		Origin, HitResult.ImpactPoint, HitResult.ImpactNormal);
	const FVector Direction = UKismetMathLibrary::GetDirectionUnitVector(ProjectedOrigin, HitResult.ImpactPoint);

	HitResult.ImpactPoint = HitResult.ImpactPoint - Direction;
}

// ─────────────────────────────────────────────────────────────────────────────
//  SetTraceHitPoint
//  直接替换命中点的 ImpactPoint。
// ─────────────────────────────────────────────────────────────────────────────
void UTraversalCalculationsFunctionLibrary::SetTraceHitPoint(UTraversalComponent* TraversalComponent,
	FHitResult& HitResult, FVector NewImpactPoint)
{
	HitResult.ImpactPoint = NewImpactPoint;
}

// ─────────────────────────────────────────────────────────────────────────────
//  TraceCorners
//  检测命中点是否靠近物体角落并计算偏移后的安全点：
//    - TraceAlongHitPlane 沿反方向追踪
//    - HalfWidth = MinLedgeWidth / 2
//    - 若追踪命中的点距原始点小于 HalfWidth，则视为靠近角落
//    - 返回的 OffsettedCornerPoint 为远离角落的偏移坐标
// ─────────────────────────────────────────────────────────────────────────────
void UTraversalCalculationsFunctionLibrary::TraceCorners(UTraversalComponent* TraversalComponent, const FHitResult& Hit,
	FVector TraceDirection, float TraceLength, FVector& OffsettedCornerPoint, bool& CloseToCorner,
	double& DistanceToCorner)
{
	FHitResult OutHit;
	const bool bHit = TraceAlongHitPlane(TraversalComponent, Hit, TraceLength, TraceDirection, OutHit);

	if (bHit)
	{
		const double HalfWidth = TraversalComponent->MinLedgeWidth / 2.0;

		OffsettedCornerPoint = OutHit.ImpactPoint + (-TraceDirection * HalfWidth);
		DistanceToCorner = FVector::Distance(OutHit.ImpactPoint, Hit.ImpactPoint);
		CloseToCorner = DistanceToCorner < HalfWidth;
	}
	else
	{
		OffsettedCornerPoint = FVector::ZeroVector;
		CloseToCorner = false;
		DistanceToCorner = 0.0;
	}
}

// ─────────────────────────────────────────────────────────────────────────────
//  TraceWidth
//  宽度方向的双向表面连续性追踪：
//    HalfWidth = MinLedgeWidth / 2
//    DepthOffset = ImpactNormal × MinFrontLedgeDepth
//    TraceStart = ImpactPoint + Direction × HalfWidth + DepthOffset
//    TraceEnd   = ImpactPoint + Direction × HalfWidth - DepthOffset
//  沿着 Direction 方向偏移后，在深度范围 [−MinFrontLedgeDepth, +MinFrontLedgeDepth]
//  内进行线条追踪，检测表面在指定宽度处是否连续存在。
// ─────────────────────────────────────────────────────────────────────────────
bool UTraversalCalculationsFunctionLibrary::TraceWidth(UTraversalComponent* TraversalComponent, const FHitResult& Hit,
                                                       FVector Direction)
{
	const FVector ImpactPoint = Hit.ImpactPoint;
	const FVector ImpactNormal = Hit.ImpactNormal;
	UPrimitiveComponent* HitComponent = Hit.Component.Get();

	const double HalfWidth = TraversalComponent->MinLedgeWidth / 2.0;
	const FVector Offset = Direction * HalfWidth;
	const FVector DepthOffset = ImpactNormal * TraversalComponent->MinFrontLedgeDepth;

	const FVector TraceStart = ImpactPoint + Offset + DepthOffset;
	const FVector TraceEnd = ImpactPoint + Offset - DepthOffset;

	if (!HitComponent)
	{
		return false;
	}

	FVector HitLocation;
	FVector HitNormal;
	FName BoneName;
	FHitResult OutHit;

	return HitComponent->K2_LineTraceComponent(TraceStart, TraceEnd, TraversalComponent->bTraceComplex,
	                                           TraversalComponent->bShowTrace,
	                                           TraversalComponent->bPersistentShowTrace, HitLocation, HitNormal,
	                                           BoneName, OutHit);
}
