// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"

#include "CommonGameplay/Player/Data/CharacterMovementData.h"

#include "PoseSearch/PoseSearchHistory.h"
#include "UObject/Interface.h"
#include "Interface_MotionMatching.generated.h"

// This class does not need to be modified.
UINTERFACE(MinimalAPI,Blueprintable)
class UInterface_MotionMatching : public UInterface
{
	GENERATED_BODY()
};

/**
 * 
 */
class UMWSAMPLEPREVIEW_API IInterface_MotionMatching
{
	GENERATED_BODY()

	// Add interface functions to this class. This is the class that will be inherited to implement this interface.
public:
	UFUNCTION(BlueprintCallable, BlueprintNativeEvent, Category="Interface|Getters", DisplayName="获取姿势历史",meta=(BlueprintThreadSafe))
	FPoseHistoryReference GetPoseHistory() const;

	UFUNCTION(BlueprintCallable, BlueprintNativeEvent, Category="Interface|Getters", DisplayName="获取迭代变换",meta=(BlueprintThreadSafe))
	FTransform GetInteractionTransform();

	UFUNCTION(BlueprintCallable, BlueprintNativeEvent, Category="Interface|Getters", DisplayName="获取步态",meta=(BlueprintThreadSafe))
	EGait GetGait() const;

	UFUNCTION(BlueprintCallable, BlueprintNativeEvent, Category="Interface|Setters", DisplayName="设置迭代变换",meta=(BlueprintThreadSafe))
	void SetInteractionTransform(UPARAM(DisplayName="迭代变换")
		const FTransform& InteractionTransform);

	UFUNCTION(BlueprintCallable, BlueprintNativeEvent, Category="Interface|Setters", DisplayName="设置通知变换-重新过渡",meta=(BlueprintThreadSafe))
	void SetNotifyTransform_Retransition(bool bNewTransform);

	UFUNCTION(BlueprintCallable, BlueprintNativeEvent, Category="Interface|Setters", DisplayName="设置通知变换-循环",meta=(BlueprintThreadSafe))
	void SetNotifyTransform_ToLoop(bool bNewTransform);
};
