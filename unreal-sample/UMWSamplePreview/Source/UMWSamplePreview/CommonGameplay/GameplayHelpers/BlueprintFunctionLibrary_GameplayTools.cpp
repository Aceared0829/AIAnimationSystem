// Fill out your copyright notice in the Description page of Project Settings.


#include "BlueprintFunctionLibrary_GameplayTools.h"
#include "EnhancedInputSubsystems.h"

#include "Engine/LocalPlayer.h"
#include "Engine/World.h"

#include "GameFramework/PlayerController.h"

#include "Kismet/GameplayStatics.h"


FInputActionValue UBlueprintFunctionLibrary_GameplayTools::GetInputActionValue(UInputAction* InputAction)
{
	if (const APlayerController* PC = Cast<APlayerController>(GWorld->GetFirstPlayerController()))
	{
		const UEnhancedInputLocalPlayerSubsystem* Subsystem =
			ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(PC->GetLocalPlayer());
		if (Subsystem)
		{
			return Subsystem->GetPlayerInput()->GetActionValue(InputAction);
		}
	}
	return FInputActionValue();
}


bool UBlueprintFunctionLibrary_GameplayTools::GetInputActionValue_Bool(UInputAction* InputAction)
{
	const FInputActionValue Value = GetInputActionValue(InputAction);
	return Value.Get<bool>();
}

float UBlueprintFunctionLibrary_GameplayTools::GetInputActionValue_Float(UInputAction* InputAction)
{
	const FInputActionValue Value = GetInputActionValue(InputAction);
	return Value.Get<float>();
}

FVector2D UBlueprintFunctionLibrary_GameplayTools::GetInputActionValue_Vector2D(UInputAction* InputAction)
{
	const FInputActionValue Value = GetInputActionValue(InputAction);
	return Value.Get<FVector2D>();
}

FVector UBlueprintFunctionLibrary_GameplayTools::GetInputActionValue_Vector(UInputAction* InputAction)
{
	const FInputActionValue Value = GetInputActionValue(InputAction);
	return Value.Get<FVector>();
}
