// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Data/CharacterMovementData.h"
#include "GameFramework/Character.h"

#include "Interfaces/Interface_PlayerCharacter.h"

#include "CharacterBase.generated.h"

class USoundWave;
class UFoleyEventsComponent;
class UMotionWarpingComponent;
struct FInputActionValue;
class UInputAction;
class UPreCMCTick;

/**
 * 角色运动驱动层提交给 CharacterBase 的单帧意图。
 * 子类只描述期望运动，CMC 参数仍由 CharacterBase 统一应用。
 */
struct UMWSAMPLEPREVIEW_API FCharacterMovementIntent
{
	EGait DesiredGait = Run;
	FVector MovementDirection = FVector::ZeroVector;
	FRotator OrientationIntent = FRotator::ZeroRotator;
	bool bHasMovementIntent = false;
	bool bOrientRotationToMovement = true;
	bool bUseControllerDesiredRotation = false;
	bool bUseRequestedMoveAcceleration = true;
};

UCLASS(Blueprintable)
class UMWSAMPLEPREVIEW_API ACharacterBase : public ACharacter,public IInterface_PlayerCharacter
{
	GENERATED_BODY()

public:
	// Sets default values for this character's properties
	ACharacterBase();
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,DisplayName="运动扭曲组件",Category="组件")
	TObjectPtr<UMotionWarpingComponent> MotionWarpingComponent;

	UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="组件")
	TObjectPtr<UFoleyEventsComponent> FoleyEventsComp;
protected:

	virtual void BeginPlay() override;
	
	virtual void PossessedBy(AController* NewController) override;

	/**
	 * 构建当前帧运动意图。默认实现保留现有玩家输入规则，AI 等子类只需覆盖意图来源。
	 */
	virtual void BuildMovementIntent(FCharacterMovementIntent& OutIntent) const;

	/** 根据统一意图计算制动值，避免共享执行层再次读取具体输入设备。 */
	float CalculateBrakingDecelerationForMovementIntent(const FCharacterMovementIntent& MovementIntent) const;

public:
	// Called every frame
	virtual void Tick(float DeltaTime) override;
	
	// Called to bind functionality to input
	virtual void SetupPlayerInputComponent(class UInputComponent* PlayerInputComponent) override;
	
	virtual void GetLifetimeReplicatedProps(TArray<class FLifetimeProperty>& OutLifetimeProps) const override;
	
	//因为我们没有任何下蹲掉落或着陆的动画，所以每当角色从悬崖掉下来时，这个事件会简单地取消下蹲状态。
	virtual void OnWalkingOffLedge_Implementation(const FVector& PreviousFloorImpactNormal, const FVector& PreviousFloorContactNormal, const FVector& PreviousLocation, float TimeDelta) override;
	
	/*
	 * 关于为什么要添加CanUpdateCmc的说明：
	 * 由于BlueprintNativeEvent的函数在蓝图中重写后，C++中对应的实现函数（即CanUpdateCMC_Implementation）将不会被调用。
	 * 这意味着如果我们只使用CanUpdateCMC，那么在蓝图中重写该函数后，C++的逻辑将无法执行。
	 * 为了解决这个问题，我们添加了一个普通的虚函数CanUpdateCmc。
	 * 这样，无论是在C++中还是在蓝图中，我们都可以确保相关的逻辑能够被正确执行
	 * 
	 * 并且这么做比起官方蓝图来说还有一些好处，万一之后我们引入了其他的移动手段
	 * 我们可以直接在C++中重写CanUpdateCmc函数，而不需要每次都去蓝图中修改
	 * 这么将会更自由一些
	 */
private:
	UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="移动",meta=(AllowPrivateAccess="true"))
	TObjectPtr<UPreCMCTick> PreCMCTickComponent;

public:
	UFUNCTION(Client,BlueprintCallable,Unreliable)
	void OnPossessedByClient_Event();

	UFUNCTION(BlueprintNativeEvent,BlueprintCallable,DisplayName="可否更新CMC",Category="移动")
	bool CanUpdateCMC();
	virtual bool CanUpdateCmc();
	
	UFUNCTION(BlueprintCallable,DisplayName="更新CMC旋转",Category="移动")
	void UpdateCMCRotation();
	
	UFUNCTION(BlueprintCallable,DisplayName="更新CMC运动",Category="移动")
	void UpdateCMCMovement();

public:
	UPROPERTY(EditAnywhere, BlueprintReadWrite, DisplayName="移动遥感模式", Category="输入")
	TEnumAsByte<EAnalogStickBehavior> MovementStickMode = FixedSpeed_SingleGait;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,DisplayName="遥感走路/跑步阈值",Category="输入")
	float AnalogWalkRunThreshold = 0.5f;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,Replicated,Category="输入",DisplayName="角色输入状态")
	FMovementInputState CharacterInputState;
	
	UFUNCTION(BlueprintCallable,Category="输入",Server,Unreliable,DisplayName="更新角色输入状态-服务器")
	void UpdateCharacterInputState_Server(const FMovementInputState& NewMovementInputState);
	
	UFUNCTION(BlueprintCallable,Category="输入",DisplayName="获取移动输入规模值")
	FVector2D GetMovementInputScaleValue(const FVector2D& InputVector2D) const;

public:
	UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Camera")
	TEnumAsByte<ECameraStyle> CameraStyle = Medium;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,DisplayName="扫射速度映射曲线",Category="移动")
	TObjectPtr<UCurveFloat> StrafeSpeedMappingCurve;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,Replicated,DisplayName="步态",Category="移动")
	TEnumAsByte<EGait> Gait = Run;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,DisplayName="行走速度",Category="移动")
	FVector WalkSpeed = FVector(200.0f, 180.0f, 150.0f);
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,DisplayName="跑步速度",Category="移动")
	FVector RunSpeed = FVector(500.0f, 350.0f,300.0f);
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,DisplayName="冲刺速度",Category="移动")
	FVector SprintSpeed = FVector(700.0f, 700.0f,700.0f);
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,DisplayName="蹲伏速度",Category="移动")
	FVector CrouchSpeed = FVector(200.0f, 200.0f,200.0f);
	
	UFUNCTION(BlueprintCallable,DisplayName="获取期望步态",Category="移动")
	EGait GetDesiredGait() const;
	
	UFUNCTION(BlueprintCallable,BlueprintPure,DisplayName="计算最大加速度",Category="移动")
	float CalculateMaxAcceleration() const;
	
	UFUNCTION(BlueprintCallable,BlueprintPure,DisplayName="计算制动减速度",Category="移动")
	float CalculateBrakingDeceleration() const;
	
	UFUNCTION(BlueprintCallable,BlueprintPure,DisplayName="计算地面摩擦系数",Category="移动")
	float CalculateGroundFriction() const;
	
	UFUNCTION(BlueprintCallable,BlueprintPure,DisplayName="计算最大速度",Category="移动")
	float CalculateMaxSpeed() const;
	
	UFUNCTION(BlueprintCallable,BlueprintPure,DisplayName="计算最大蹲伏速度",Category="移动")
	float CalculateMaxCrouchSpeed() const;
	
	UFUNCTION(BlueprintCallable,BlueprintPure,DisplayName="有移动输入向量",Category="移动")
	bool HasMovementInputVector() const;
	
	UFUNCTION(BlueprintCallable,DisplayName="可否冲刺",Category="移动")
	bool CanSprint() const;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,DisplayName="刚落地标志",Category="移动")
	bool bJustLanded = false;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,DisplayName="落地速度",Category="移动")
	FVector LandVelocity = FVector::ZeroVector;
	
private:
	UPROPERTY(VisibleAnywhere,BlueprintReadWrite,DisplayName="上一帧是否在地面—模拟",Category="模拟",
		meta=(AllowPrivateAccess = true))
	bool bWasMovingOnGroundLastFrame_Simulated = true;
	
	UPROPERTY(VisibleAnywhere,BlueprintReadWrite,DisplayName="上一帧更新的速度",Category="模拟",
		meta=(AllowPrivateAccess = true))
	TArray<FVector> LastUpdateVelocity;

	/** 非 Strafe 下最近一次有效面向，松手后继续作为 OrientationIntent，避免回弹到镜头朝向。 */
	mutable FRotator LastOrientToMovementIntent = FRotator::ZeroRotator;

	mutable bool bHasLastOrientToMovementIntent = false;

public:
	UFUNCTION(BlueprintCallable,DisplayName="角色移动过更新事件",Category="模拟")
	void OnCharacterMovementUpdateEvent(float DeltaTime,FVector OldLocation, FVector OldVelocity);
	
	UFUNCTION(BlueprintCallable,DisplayName="更新模拟移动",Category="模拟")
	void UpdateMovementSimulated(const FVector& OldVelocity);
	
	virtual void OnJumped_Implementation() override;
	virtual void Landed(const FHitResult& Hit) override;
	
	UFUNCTION(BlueprintCallable,BlueprintNativeEvent,DisplayName="落地时触发事件",Category="模拟")
	void OnLanded_Event(FVector InLandVelocity);
	
	UFUNCTION(BlueprintCallable,BlueprintNativeEvent,DisplayName="跳跃时触发事件",Category="模拟")
	void OnJumped_Event(float GroundSpeedBeforeJump);

public:
	virtual void SetCharacterInputState_Implementation(FMovementInputState NewInputState) override;
	virtual FCharacterPropertiesForAnimation GetCharacterPropertiesForAnimation_Implementation() const override;
	virtual FCharacterPropertiesForCamera GetCharacterPropertiesForCamera_Implementation() const override;
	virtual FCharacterPropertiesForTraversal GetCharacterPropertiesForTraversal_Implementation() const override;
	
};
