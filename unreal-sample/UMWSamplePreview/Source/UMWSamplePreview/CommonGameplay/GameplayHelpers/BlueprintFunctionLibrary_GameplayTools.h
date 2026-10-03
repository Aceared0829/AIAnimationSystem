// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "InputActionValue.h"

#include "Kismet/BlueprintFunctionLibrary.h"
#include "BlueprintFunctionLibrary_GameplayTools.generated.h"

class UInputAction;
/**
 *
 */
UCLASS()
class UMWSAMPLEPREVIEW_API UBlueprintFunctionLibrary_GameplayTools : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintPure,BlueprintCallable, DisplayName="获取InputAction的值",Category="输入|工具")
	static FInputActionValue GetInputActionValue(UPARAM(DisplayName="输入动作") UInputAction* InputAction);

	UFUNCTION(BlueprintPure,BlueprintCallable, DisplayName="获取InputAction的值-布尔",Category="输入|工具")
	static bool GetInputActionValue_Bool(UPARAM(DisplayName="输入动作") UInputAction* InputAction);

	UFUNCTION(BlueprintPure,BlueprintCallable, DisplayName="获取InputAction的值-浮点",Category="输入|工具")
	static float GetInputActionValue_Float(UPARAM(DisplayName="输入动作") UInputAction* InputAction);

	UFUNCTION(BlueprintPure,BlueprintCallable, DisplayName="获取InputAction的值-向量2D",Category="输入|工具")
	static FVector2D GetInputActionValue_Vector2D(UPARAM(DisplayName="输入动作") UInputAction* InputAction);

	UFUNCTION(BlueprintPure,BlueprintCallable, DisplayName="获取InputAction的值-向量",Category="输入|工具")
	static FVector GetInputActionValue_Vector(UPARAM(DisplayName="输入动作") UInputAction* InputAction);

};
