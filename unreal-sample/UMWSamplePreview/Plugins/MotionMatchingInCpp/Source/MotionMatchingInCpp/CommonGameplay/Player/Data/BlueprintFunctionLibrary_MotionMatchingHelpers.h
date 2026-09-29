// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "BlueprintFunctionLibrary_MotionMatchingHelpers.generated.h"

USTRUCT(Blueprintable)
struct FDebugGraphLineProperties
{
	GENERATED_BODY()
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	FString Name;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	FLinearColor Color;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	TArray<float> Values;
};

UCLASS()
class MOTIONMATCHINGINCPP_API UBlueprintFunctionLibrary_MotionMatchingHelpers : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

	UFUNCTION(BlueprintCallable, DisplayName="添加到字符串历史数组", Category="MotionMatching|Helpers")
	static void AddToStringHistoryArray(UPARAM(ref, DisplayName="输入输出字符串数组") TArray<FString>& InOutValues,
	                                    UPARAM(DisplayName="新值") const FString& NewValue,
	                                    UPARAM(DisplayName="最大历史长度") int32 MaxHistoryLength);

	UFUNCTION(BlueprintCallable, DisplayName="获取Object名称", Category="MotionMatching|Helpers")
	static TArray<FString> GetObjectNames(UPARAM(ref,DisplayName="对象") const TArray<UObject*> Objects);

	UFUNCTION(BlueprintCallable, DisplayName="获取带有CVAR的Pawn类", Category = "MotionMatching|Helpers")
	static TSubclassOf<APawn> GetPawnClassWithCVAR(
		UPARAM(ref, DisplayName="Pawn类")TArray<TSubclassOf<APawn>>& PawnClasses,
		UPARAM(DisplayName="默认Pawn类") TSubclassOf<APawn> DefaultPawnClass);

	UFUNCTION(BlueprintCallable, DisplayName="使用CVAR获取视觉覆盖", Category="MotionMatching|Helpers")
	static TSubclassOf<AActor> GetVisualOverrideWithCVAR(
		UPARAM(ref, DisplayName="视觉覆盖s")TArray<TSubclassOf<AActor>>& VisualOverrides);
};
