// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"

#include "CommonGameplay/Player/Data/CharacterMovementData.h"
#include "CommonGameplay/Player/Data/GameplayCameraData.h"

#include "UObject/Interface.h"
#include "Interface_PlayerCharacter.generated.h"

// This class does not need to be modified.
UINTERFACE(MinimalAPI,Blueprintable)
class UInterface_PlayerCharacter : public UInterface
{
	GENERATED_BODY()
};

/**
 *
 */
class UMWSAMPLEPREVIEW_API IInterface_PlayerCharacter
{
	GENERATED_BODY()

	// Add interface functions to this class. This is the class that will be inherited to implement this interface.
public:

	UFUNCTION(BlueprintCallable,BlueprintNativeEvent,Category="Setters")
	void SetCharacterInputState(FMovementInputState NewInputState);

	UFUNCTION(BlueprintCallable,BlueprintNativeEvent,Category="Getters")
	FCharacterPropertiesForAnimation GetCharacterPropertiesForAnimation() const;

	UFUNCTION(BlueprintCallable,BlueprintNativeEvent,Category="Getters")
	FCharacterPropertiesForCamera GetCharacterPropertiesForCamera() const;

	UFUNCTION(BlueprintCallable,BlueprintNativeEvent,Category="Getters")
	FCharacterPropertiesForTraversal GetCharacterPropertiesForTraversal() const;

};
