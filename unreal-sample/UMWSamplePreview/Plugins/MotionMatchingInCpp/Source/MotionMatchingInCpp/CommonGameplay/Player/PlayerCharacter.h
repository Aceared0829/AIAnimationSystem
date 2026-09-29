// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "CharacterBase.h"
#include "PlayerCharacter.generated.h"

class UCameraComponent;
class USpringArmComponent;
class UGameplayCameraComponent;

UCLASS()
class MOTIONMATCHINGINCPP_API APlayerCharacter : public ACharacterBase
{
	GENERATED_BODY()

public:
	// Sets default values for this character's properties
	APlayerCharacter();
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="组件",meta=(AllowPrivateAccess="true"))
	TObjectPtr<UGameplayCameraComponent> GameplayPlayerCamera;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="组件",meta=(AllowPrivateAccess="true"))
	TObjectPtr<USpringArmComponent> SpringArm;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="组件",meta=(AllowPrivateAccess="true"))
	TObjectPtr<UCameraComponent> Camera;

	UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="组件|摄像机",meta=(AllowPrivateAccess="true"))
	bool bGameplayCameraActivated = true;
protected:
	// Called when the game starts or when spawned
	virtual void BeginPlay() override;

	UFUNCTION(BlueprintCallable,DisplayName="设置摄像机",Category="摄像机")
	void SetupCamera();
	
	virtual void OnPossessedByClient_Event_Implementation() override;
	
public:
	// Called every frame
	virtual void Tick(float DeltaTime) override;

	// Called to bind functionality to input
	virtual void SetupPlayerInputComponent(class UInputComponent* PlayerInputComponent) override;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="输入|映射",DisplayName="移动操作")
	TObjectPtr<UInputAction> MoveAction;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="输入|映射",DisplayName="移动-世界空间操作")
	TObjectPtr<UInputAction> MoveAction_WorldSpace;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="输入|映射",DisplayName="观察操作")
	TObjectPtr<UInputAction> LookAction;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="输入|映射",DisplayName="观察-手柄操作")
	TObjectPtr<UInputAction> LookAction_Gamepad;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="输入|映射",DisplayName="步行操作")
	TObjectPtr<UInputAction> WalkAction;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="输入|映射",DisplayName="冲刺操作")
	TObjectPtr<UInputAction> SprintAction;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="输入|映射",DisplayName="蹲伏操作")
	TObjectPtr<UInputAction> CrouchAction;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="输入|映射",DisplayName="扫射操作")
	TObjectPtr<UInputAction> StrafeAction;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="输入|映射",DisplayName="瞄准操作")
	TObjectPtr<UInputAction> AimAction;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="输入|映射",DisplayName="摄像机切换操作")
	TObjectPtr<UInputAction> CameraSwitchAction;
	
	
protected:
protected:
	UFUNCTION(BlueprintCallable,DisplayName="移动",Category="输入")
	void Move(const FInputActionValue& Value);
	
	UFUNCTION(BlueprintCallable,DisplayName="移动-世界空间",Category="输入")
	void Move_WorldSpace(const FInputActionValue& Value);
	
	UFUNCTION(BlueprintCallable,DisplayName="观察",Category="输入")
	void Look(const FInputActionValue& Value);
	
	UFUNCTION(BlueprintCallable,DisplayName="观察-手柄",Category="输入")
	void Look_Gamepad(const FInputActionValue& Value);
	
	UFUNCTION(BlueprintCallable,DisplayName="切换步行",Category="输入")
	void WalkToggle(const FInputActionValue& Value);
	
	UFUNCTION(BlueprintCallable,DisplayName="切换冲刺",Category="输入")
	void SprintToggle(const FInputActionValue& Value);
	
	UFUNCTION(BlueprintCallable,DisplayName="切换蹲伏",Category="输入")
	void CrouchToggle(const FInputActionValue& Value);
	
	UFUNCTION(BlueprintCallable,DisplayName="切换扫射",Category="输入")
	void StrafeToggle(const FInputActionValue& Value);
	
	UFUNCTION(BlueprintCallable,DisplayName="切换瞄准",Category="输入")
	void AimToggle(const FInputActionValue& Value);
	
	// 要修复的
	UFUNCTION(BlueprintCallable,DisplayName="摄像机切换",Category="输入")
	void CameraSwitch(const FInputActionValue& Value);
	
private:
	//临时资源管理
	UPROPERTY()
	TObjectPtr<USoundWave> CameraSwitchSound;
};
