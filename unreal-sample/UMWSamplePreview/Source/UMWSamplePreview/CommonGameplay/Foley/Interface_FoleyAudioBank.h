// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Interface.h"
#include "Interface_FoleyAudioBank.generated.h"

// This class does not need to be modified.
UINTERFACE()
class UInterface_FoleyAudioBank : public UInterface
{
	GENERATED_BODY()
};

/**
 * 
 */
class UMWSAMPLEPREVIEW_API IInterface_FoleyAudioBank
{
	GENERATED_BODY()

	// Add interface functions to this class. This is the class that will be inherited to implement this interface.
public:
	
	UFUNCTION(BlueprintCallable,BlueprintNativeEvent)
	bool CanPlayFoleyEvent();
};
