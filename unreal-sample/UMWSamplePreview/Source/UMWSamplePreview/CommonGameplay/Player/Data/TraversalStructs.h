// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "CharacterMovementData.h"
#include "PoseSearch/PoseSearchHistory.h"
#include "TraversalStructs.generated.h"

class UPrimitiveComponent;
class UAnimMontage;

UENUM(BlueprintType,DisplayName="跑酷动作形式")
enum class ETraversalActionType : uint8
{
	None UMETA(DisplayName="无"),
	Hurdle UMETA(DisplayName="跨越"),
	Vault UMETA(DisplayName="翻越"),
	Mantle UMETA(DisplayName="攀爬")
};

USTRUCT(BlueprintType)
struct FTraversalCheckInputs
{
	GENERATED_BODY()
	[[nodiscard]] FTraversalCheckInputs()
		: TraceForwardDirection(FVector::ZeroVector)
		  , TraceForwardDistance(0.0)
		  , TraceOriginOffset(FVector::ZeroVector)
		  , TraceEndOffset(FVector::ZeroVector)
		  , TraceRadius(0.0)
		  , TraceHalfHeight(0.0)
	{
	}

	[[nodiscard]] FTraversalCheckInputs(
		const FVector& InTraceForwardDirection,
		double InTraceForwardDistance,
		const FVector& InTraceOriginOffset,
		const FVector& InTraceEndOffset,
		double InTraceRadius,
		double InTraceHalfHeight)
		: TraceForwardDirection(InTraceForwardDirection)
		  , TraceForwardDistance(InTraceForwardDistance)
		  , TraceOriginOffset(InTraceOriginOffset)
		  , TraceEndOffset(InTraceEndOffset)
		  , TraceRadius(InTraceRadius)
		  , TraceHalfHeight(InTraceHalfHeight)
	{
	}

	UPROPERTY(BlueprintReadWrite, EditAnywhere,
		meta=(DisplayName="TraceForwardDirection", MakeStructureDefaultValue="0.000000,0.000000,0.000000"))
	FVector TraceForwardDirection;

	UPROPERTY(BlueprintReadWrite, EditAnywhere,
		meta=(DisplayName="TraceForwardDistance", MakeStructureDefaultValue="0.000000"))
	double TraceForwardDistance;

	UPROPERTY(BlueprintReadWrite, EditAnywhere,
		meta=(DisplayName="TraceOriginOffset", MakeStructureDefaultValue="0.000000,0.000000,0.000000"))
	FVector TraceOriginOffset;

	UPROPERTY(BlueprintReadWrite, EditAnywhere,
		meta=(DisplayName="TraceEndOffset", MakeStructureDefaultValue="0.000000,0.000000,0.000000"))
	FVector TraceEndOffset;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="TraceRadius", MakeStructureDefaultValue="0.000000"))
	double TraceRadius;

	UPROPERTY(BlueprintReadWrite, EditAnywhere,
		meta=(DisplayName="TraceHalfHeight", MakeStructureDefaultValue="0.000000"))
	double TraceHalfHeight;
};


USTRUCT(BlueprintType)
struct FTraversalCheckResult
{
	GENERATED_BODY()

	[[nodiscard]] FTraversalCheckResult() :
		ActionType(ETraversalActionType::None)
		, bHasFrontLedge(false)
		, FrontLedgeLocation(FVector::ZeroVector)
		, FrontLedgeNormal(FVector::ZeroVector)
		, bHasBackLedge(false)
		, BackLedgeLocation(FVector::ZeroVector)
		, BackLedgeNormal(FVector::ZeroVector)
		, bHasBackFloor(false)
		, BackFloorLocation(FVector::ZeroVector)
		, ObstacleHeight(0.0)
		, ObstacleDepth(0.0)
		, BackLedgeHeight(0.0)
		, HitComponent(nullptr)
		, ChosenMontage(nullptr)
		, StartTime(0.0)
		, PlayRate(0.0)
	{
	}

	[[nodiscard]] FTraversalCheckResult(const ETraversalActionType ActionType, const bool bHasFrontLedge,
	                                    const FVector& FrontLedgeLocation, const FVector& FrontLedgeNormal,
	                                    const bool bHasBackLedge,
	                                    const FVector& BackLedgeLocation, const FVector& BackLedgeNormal,
	                                    const bool bHasBackFloor,
	                                    const FVector& BackFloorLocation, const double ObstacleHeight,
	                                    const double ObstacleDepth,
	                                    const double BackLedgeHeight,
	                                    const TObjectPtr<UPrimitiveComponent>& HitComponent,
	                                    const TObjectPtr<UAnimMontage>& ChosenMontage, const double StartTime,
	                                    const double PlayRate)
		: ActionType(ActionType),
		  bHasFrontLedge(bHasFrontLedge),
		  FrontLedgeLocation(FrontLedgeLocation),
		  FrontLedgeNormal(FrontLedgeNormal),
		  bHasBackLedge(bHasBackLedge),
		  BackLedgeLocation(BackLedgeLocation),
		  BackLedgeNormal(BackLedgeNormal),
		  bHasBackFloor(bHasBackFloor),
		  BackFloorLocation(BackFloorLocation),
		  ObstacleHeight(ObstacleHeight),
		  ObstacleDepth(ObstacleDepth),
		  BackLedgeHeight(BackLedgeHeight),
		  HitComponent(HitComponent),
		  ChosenMontage(ChosenMontage),
		  StartTime(StartTime),
		  PlayRate(PlayRate)
	{
	}

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="ActionType", MakeStructureDefaultValue="None"))
	ETraversalActionType ActionType;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="HasFrontLedge", MakeStructureDefaultValue="False"))
	bool bHasFrontLedge;

	UPROPERTY(BlueprintReadWrite, EditAnywhere,
		meta=(DisplayName="FrontLedgeLocation", MakeStructureDefaultValue="0.000000,0.000000,0.000000"))
	FVector FrontLedgeLocation;

	UPROPERTY(BlueprintReadWrite, EditAnywhere,
		meta=(DisplayName="FrontLedgeNormal", MakeStructureDefaultValue="0.000000,0.000000,0.000000"))
	FVector FrontLedgeNormal;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="HasBackLedge", MakeStructureDefaultValue="False"))
	bool bHasBackLedge;

	UPROPERTY(BlueprintReadWrite, EditAnywhere,
		meta=(DisplayName="BackLedgeLocation", MakeStructureDefaultValue="0.000000,0.000000,0.000000"))
	FVector BackLedgeLocation;

	UPROPERTY(BlueprintReadWrite, EditAnywhere,
		meta=(DisplayName="BackLedgeNormal", MakeStructureDefaultValue="0.000000,0.000000,0.000000"))
	FVector BackLedgeNormal;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="HasBackFloor", MakeStructureDefaultValue="False"))
	bool bHasBackFloor;

	UPROPERTY(BlueprintReadWrite, EditAnywhere,
		meta=(DisplayName="BackFloorLocation", MakeStructureDefaultValue="0.000000,0.000000,0.000000"))
	FVector BackFloorLocation;

	UPROPERTY(BlueprintReadWrite, EditAnywhere,
		meta=(DisplayName="ObstacleHeight", MakeStructureDefaultValue="0.000000"))
	double ObstacleHeight;

	UPROPERTY(BlueprintReadWrite, EditAnywhere,
		meta=(DisplayName="ObstacleDepth", MakeStructureDefaultValue="0.000000"))
	double ObstacleDepth;

	UPROPERTY(BlueprintReadWrite, EditAnywhere,
		meta=(DisplayName="BackLedgeHeight", MakeStructureDefaultValue="0.000000"))
	double BackLedgeHeight;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="HitComponent", MakeStructureDefaultValue="None"))
	TObjectPtr<UPrimitiveComponent> HitComponent;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="ChosenMontage", MakeStructureDefaultValue="None"))
	TObjectPtr<UAnimMontage> ChosenMontage;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="StartTime", MakeStructureDefaultValue="0.000000"))
	double StartTime;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="PlayRate", MakeStructureDefaultValue="0.000000"))
	double PlayRate;
};

USTRUCT(BlueprintType)
struct FTraversalChooserInputs
{
	GENERATED_BODY()

	[[nodiscard]] FTraversalChooserInputs():
		ActionType(ETraversalActionType::None)
		, HasFrontLedge(false)
		, HasBackLedge(false)
		, HasBackFloor(false)
		, ObstacleHeight(0.0)
		, ObstacleDepth(0.0)
		, BackLedgeHeight(0.0)
		, DistanceToLedge(0.0)
		, MovementMode(EAMovementMode::OnGround)
		, Gait(EGait::Walk)
		, Speed(0.0)
	{
	}

	[[nodiscard]] FTraversalChooserInputs(
		const ETraversalActionType InActionType,
		const bool bHasFrontLedge,
		const bool bHasBackLedge,
		const bool bHasBackFloor,
		const double InObstacleHeight,
		const double InObstacleDepth,
		const double InBackLedgeHeight,
		const double InDistanceToLedge,
		const TEnumAsByte<EAMovementMode> InMovementMode,
		const TEnumAsByte<EGait> InGait,
		const double InSpeed,
		const FPoseHistoryReference& InPoseHistory)
		: ActionType(InActionType)
		  , HasFrontLedge(bHasFrontLedge)
		  , HasBackLedge(bHasBackLedge)
		  , HasBackFloor(bHasBackFloor)
		  , ObstacleHeight(InObstacleHeight)
		  , ObstacleDepth(InObstacleDepth)
		  , BackLedgeHeight(InBackLedgeHeight)
		  , DistanceToLedge(InDistanceToLedge)
		  , MovementMode(InMovementMode)
		  , Gait(InGait)
		  , Speed(InSpeed)
		  , PoseHistory(InPoseHistory)
	{
	}

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="ActionType"))
	ETraversalActionType ActionType;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="HasFrontLedge", MakeStructureDefaultValue="False"))
	bool HasFrontLedge;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="HasBackLedge", MakeStructureDefaultValue="False"))
	bool HasBackLedge;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="HasBackFloor", MakeStructureDefaultValue="False"))
	bool HasBackFloor;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="ObstacleHeight", MakeStructureDefaultValue="0.000000"))
	double ObstacleHeight;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="ObstacleDepth", MakeStructureDefaultValue="0.000000"))
	double ObstacleDepth;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="BackLedgeHeight", MakeStructureDefaultValue="0.000000"))
	double BackLedgeHeight;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="DistanceToLedge", MakeStructureDefaultValue="0.000000"))
	double DistanceToLedge;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="MovementMode", MakeStructureDefaultValue="OnGround"))
	TEnumAsByte<EAMovementMode> MovementMode;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="步态", MakeStructureDefaultValue="Walk"))
	TEnumAsByte<EGait> Gait;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="Speed", MakeStructureDefaultValue="0.000000"))
	double Speed;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="PoseHistory", MakeStructureDefaultValue="()"))
	FPoseHistoryReference PoseHistory;
};

USTRUCT(BlueprintType)
struct FTraversalChooserOutputs
{
	GENERATED_BODY()
	[[nodiscard]] FTraversalChooserOutputs():
		ActionType(ETraversalActionType::None)
		, MontageStartTime(0.0)
	{
	}

	[[nodiscard]] FTraversalChooserOutputs(
		const ETraversalActionType InActionType,
		const double InMontageStartTime)
		: ActionType(InActionType)
		  , MontageStartTime(InMontageStartTime)
	{
	}

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="ActionType"))
	ETraversalActionType ActionType;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="MontageStartTime", MakeStructureDefaultValue="0.000000"))
	double MontageStartTime;

};
