// Fill out your copyright notice in the Description page of Project Settings.


#include "AnimPlayerController.h"

#include "EnhancedInputSubsystems.h"

#include "Engine/LocalPlayer.h"



void AAnimPlayerController::BeginPlay()
{
	Super::BeginPlay();
	if (ULocalPlayer* LocalPlayer = GetLocalPlayer())
	{
		if (UEnhancedInputLocalPlayerSubsystem* Subsystem = LocalPlayer->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>())
		{
			// 默认加载通用输入映射文本
			if (InputMappingContexts.Contains(ECharacterState::Common))
			{
				Subsystem->AddMappingContext(InputMappingContexts[ECharacterState::Common],0);
			}
		}
	}
}

void AAnimPlayerController::SwitchInputMappingContextByCharacterState(const ECharacterState& NewInputState)
{
	ULocalPlayer* LocalPlayer = GetLocalPlayer();
	if (!LocalPlayer)
	{
		UE_LOG(LogTemp,Warning,TEXT("AnimPlayerController::SwitchInputMappingContextByCharacterState: LocalPlayer is nullptr"));
		return;
	}
	UEnhancedInputLocalPlayerSubsystem* Subsystem = LocalPlayer->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>();
	if (!Subsystem)
	{
		UE_LOG(LogTemp,Warning,TEXT("AnimPlayerController::SwitchInputMappingContextByCharacterState: EnhancedInputLocalPlayerSubsystem is nullptr"));
		return;
	}
	for (const TTuple<ECharacterState, TObjectPtr<UInputMappingContext>>& InputState : InputMappingContexts)
	{
		//如果是当前状态，则添加映射文本
		if (NewInputState == ECharacterState::Common)
		{
			continue;
		}
		else if (NewInputState == InputState.Key)
		{
			//添加映射文本
			if (!Subsystem->HasMappingContext(InputMappingContexts[NewInputState]))
			{
				Subsystem->AddMappingContext(InputMappingContexts[NewInputState],0);
			}
		}
		else
		{
			//移除映射文本
			if (Subsystem->HasMappingContext(InputMappingContexts[InputState.Key]))
			{
				Subsystem->RemoveMappingContext(InputMappingContexts[InputState.Key]);
			}
		}
	}
}
