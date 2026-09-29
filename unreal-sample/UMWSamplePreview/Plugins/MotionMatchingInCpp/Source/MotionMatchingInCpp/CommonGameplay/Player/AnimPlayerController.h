// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "AnimPlayerController.generated.h"

class UInputMappingContext;

//要通过活动状态的改变去驱动不同的输入映射文本
UENUM(BlueprintType)
enum class ECharacterState: uint8
{
	Common UMETA(DisplayName="通用"),
	Ground UMETA(DisplayName="地面"),
	Aerial UMETA(DisplayName="空中"),
	Swimming UMETA(DisplayName="游泳"),
	Cinematic UMETA(DisplayName="过场动画")
};

UCLASS()
class MOTIONMATCHINGINCPP_API AAnimPlayerController : public APlayerController
{
	GENERATED_BODY()

	virtual void BeginPlay() override;
	
public:
	UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="输入|映射",DisplayName="映射文本",meta=(AllowPrivateAccess="true"));
	TMap<ECharacterState,TObjectPtr<UInputMappingContext>> InputMappingContexts;
	
	UFUNCTION(BlueprintCallable,DisplayName="根据角色状态切换输入映射文本",Category="输入")
	void SwitchInputMappingContextByCharacterState(const ECharacterState& NewInputState);
};
