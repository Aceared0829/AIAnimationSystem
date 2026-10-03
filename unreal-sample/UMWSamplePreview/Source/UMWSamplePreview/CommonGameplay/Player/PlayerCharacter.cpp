// Fill out your copyright notice in the Description page of Project Settings.


#include "PlayerCharacter.h"

#include "EnhancedInputComponent.h"

#include "Camera/CameraComponent.h"

#include "Components/SkeletalMeshComponent.h"

#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/GameplayCameraComponent.h"
#include "GameFramework/SpringArmComponent.h"

#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetMathLibrary.h"
#include "Sound/SoundWave.h"
#include "Core/CameraAsset.h"

#include "GameFramework/GameplayCamerasPlayerCameraManager.h"

#include "UObject/ConstructorHelpers.h"


// Sets default values
APlayerCharacter::APlayerCharacter()
{
	// Set this character to call Tick() every frame.  You can turn this off to improve performance if you don't need it.
	PrimaryActorTick.bCanEverTick = true;
	
	SpringArm = CreateDefaultSubobject<USpringArmComponent>(TEXT("SpringArmComp"));
	checkf(SpringArm,TEXT("PlayerCharacter必须拥有SpringArm组件"));
	SpringArm->SetRelativeLocation(FVector{0.0f,0.0f,12.0f});
	SpringArm->SetupAttachment(RootComponent);
	SpringArm->bUsePawnControlRotation = true;
	SpringArm->bEnableCameraLag = true;
	
	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("CameraComponent"));
	checkf(Camera,TEXT("PlayerCharacter必须拥有Camera组件"));
	Camera->SetupAttachment(SpringArm);
	Camera->bAutoActivate = false;
	
	GameplayPlayerCamera = CreateDefaultSubobject<UGameplayCameraComponent>(TEXT("PlayerCameraComponent"));
	checkf(GameplayPlayerCamera,TEXT("PlayerCharacter必须拥有PlayerCamera组件"));
	GameplayPlayerCamera->SetupAttachment(GetMesh());
	GameplayPlayerCamera->SetRelativeLocation(FVector::ZeroVector);
	GameplayPlayerCamera->SetRelativeRotation(FRotator{-0.0f,90.0f,0.0f});
	if (const ConstructorHelpers::FObjectFinder<UCameraAsset> CameraAssetPath
		(TEXT("/Script/GameplayCameras.CameraAsset'/Game/Blueprints/Cameras/CameraAsset_SandboxCharacter.CameraAsset_SandboxCharacter'"));
		CameraAssetPath.Succeeded())
	{
		GameplayPlayerCamera->CameraReference.SetCameraAsset(CameraAssetPath.Object.Get());
	}
	else
	{
		GameplayPlayerCamera->CameraReference.SetCameraAsset(nullptr);
	}
	
	//默认输入映射
	if (const ConstructorHelpers::FObjectFinder<UInputAction> MoveActionPath
		(TEXT("/Script/EnhancedInput.InputAction'/Game/Input/IA_Move.IA_Move'"));
		MoveActionPath.Succeeded())
	{
		MoveAction = MoveActionPath.Object;
	}
	else
	{
		MoveAction = nullptr;
	}
	
	if (const ConstructorHelpers::FObjectFinder<UInputAction> MoveAction_WorldSpacePath
		(TEXT("/Script/EnhancedInput.InputAction'/Game/Input/IA_Move_WorldSpace.IA_Move_WorldSpace'"));
		MoveAction_WorldSpacePath.Succeeded())
	{
		MoveAction_WorldSpace = MoveAction_WorldSpacePath.Object;
	}
	else
	{
		MoveAction_WorldSpace = nullptr;
	}
	
	if (const ConstructorHelpers::FObjectFinder<UInputAction> LookActionPath
		(TEXT("/Script/EnhancedInput.InputAction'/Game/Input/IA_Look.IA_Look'"));
		LookActionPath.Succeeded())
	{
		LookAction = LookActionPath.Object;
	}
	else
	{
		LookAction = nullptr;
	}
	
	if (const ConstructorHelpers::FObjectFinder<UInputAction> LookAction_GamepadPath
		(TEXT("/Script/EnhancedInput.InputAction'/Game/Input/IA_Look_Gamepad.IA_Look_Gamepad'"));
		LookAction_GamepadPath.Succeeded())
	{
		LookAction_Gamepad = LookAction_GamepadPath.Object;
	}
	else
	{
		LookAction_Gamepad = nullptr;
	}
	
	if (const ConstructorHelpers::FObjectFinder<UInputAction> WalkActionPath
		(TEXT("/Script/EnhancedInput.InputAction'/Game/Input/IA_Walk.IA_Walk'"));
		WalkActionPath.Succeeded())
	{
		WalkAction = WalkActionPath.Object;
	}
	else
	{
		WalkAction = nullptr;
	}
	
	if (const ConstructorHelpers::FObjectFinder<UInputAction> SprintActionPath
		(TEXT("/Script/EnhancedInput.InputAction'/Game/Input/IA_Sprint.IA_Sprint'"));
		SprintActionPath.Succeeded())
	{
		SprintAction = SprintActionPath.Object;
	}
	else
	{
		SprintAction = nullptr;
	}
	
	if (const ConstructorHelpers::FObjectFinder<UInputAction> CrouchActionPath
		(TEXT("/Script/EnhancedInput.InputAction'/Game/Input/IA_Crouch.IA_Crouch'"));
		CrouchActionPath.Succeeded())
	{
		CrouchAction = CrouchActionPath.Object;
	}
	else
	{
		CrouchAction = nullptr;
	}
	
	if (const ConstructorHelpers::FObjectFinder<UInputAction> StrafeActionPath
		(TEXT("/Script/EnhancedInput.InputAction'/Game/Input/IA_Strafe.IA_Strafe'"));
		StrafeActionPath.Succeeded())
	{
		StrafeAction = StrafeActionPath.Object;
	}
	else
	{
		StrafeAction = nullptr;
	}
	
	if (const ConstructorHelpers::FObjectFinder<UInputAction> AimActionPath
		(TEXT("/Script/EnhancedInput.InputAction'/Game/Input/IA_Aim.IA_Aim'"));
		AimActionPath.Succeeded())
	{
		AimAction = AimActionPath.Object;
	}
	else
	{
		AimAction = nullptr;
	}
	
	if (const ConstructorHelpers::FObjectFinder<UInputAction> MouseWheelUpActionPath
		(TEXT("/Script/EnhancedInput.InputAction'/Game/Input/IA_CameraSwitch.IA_CameraSwitch'"));
		MouseWheelUpActionPath.Succeeded())
	{
		CameraSwitchAction = MouseWheelUpActionPath.Object;
	}
	else
	{
		CameraSwitchAction = nullptr;
	}
	
	if (ConstructorHelpers::FObjectFinder<USoundWave> SoundPath(
		TEXT(
			"/Script/Engine.SoundWave'/Engine/VREditor/Sounds/UI/Object_Snaps_To_Another_Actor.Object_Snaps_To_Another_Actor'"))
	;
	SoundPath.Succeeded())
	{
		CameraSwitchSound = SoundPath.Object.Get();
	}
	else
	{
		CameraSwitchSound = nullptr;
	}
}

// Called when the game starts or when spawned
void APlayerCharacter::BeginPlay()
{
	Super::BeginPlay();
	
}

void APlayerCharacter::SetupCamera()
{
	// 只给本地玩家设置相机
	if (!IsLocallyControlled())
	{
		return;
	}

	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!PC)
	{
		UE_LOG(LogTemp, Warning, TEXT("PlayerCharacter::SetupCamera(): PlayerController is nullptr (Controller=%s)"),
			   *GetNameSafe(GetController()));
		return;
	}
	if (bGameplayCameraActivated)
	{
		GameplayPlayerCamera->ActivateCameraForPlayerController(PC, true);
	}
	else
	{
		Camera->Activate();
		PC->SetViewTargetWithBlend(this, false, EViewTargetBlendFunction::VTBlend_Linear, 0.0f, false);
	}
}


void APlayerCharacter::OnPossessedByClient_Event_Implementation()
{
	Super::OnPossessedByClient_Event_Implementation();
	SetupCamera();
}

// Called every frame
void APlayerCharacter::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
}

// Called to bind functionality to input
void APlayerCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);
	if (UEnhancedInputComponent* EnhancedInputComponent = Cast<UEnhancedInputComponent>(PlayerInputComponent))
	{
		// 逐一绑定所有输入动作，保证可扩展性
		if (MoveAction)
		{
			EnhancedInputComponent->BindAction(MoveAction,ETriggerEvent::Triggered,this,&APlayerCharacter::Move);
		}
		if (MoveAction_WorldSpace)
		{
			EnhancedInputComponent->BindAction(MoveAction_WorldSpace,ETriggerEvent::Triggered,this,&APlayerCharacter::Move_WorldSpace);
		}
		if (LookAction)
		{
			EnhancedInputComponent->BindAction(LookAction,ETriggerEvent::Triggered,this,&APlayerCharacter::Look);
		}
		if (LookAction_Gamepad)
		{
			EnhancedInputComponent->BindAction(LookAction_Gamepad,ETriggerEvent::Triggered,this,&APlayerCharacter::Look_Gamepad);
		}
		if (WalkAction)
		{
			EnhancedInputComponent->BindAction(WalkAction,ETriggerEvent::Triggered,this,&APlayerCharacter::WalkToggle);
		}
		if (SprintAction)
		{
			EnhancedInputComponent->BindAction(SprintAction,ETriggerEvent::Triggered,this,&APlayerCharacter::SprintToggle);
		}
		if (CrouchAction)
		{
			EnhancedInputComponent->BindAction(CrouchAction,ETriggerEvent::Triggered,this,&APlayerCharacter::CrouchToggle);
		}
		if (StrafeAction)
		{
			EnhancedInputComponent->BindAction(StrafeAction,ETriggerEvent::Triggered,this,&APlayerCharacter::StrafeToggle);
		}
		if (AimAction)
		{
			EnhancedInputComponent->BindAction(AimAction,ETriggerEvent::Triggered,this,&APlayerCharacter::AimToggle);
		}
		if (CameraSwitchAction)
		{
			EnhancedInputComponent->BindAction(CameraSwitchAction,ETriggerEvent::Triggered,this,&APlayerCharacter::CameraSwitch);
		}
	}
}

void APlayerCharacter::Move(const FInputActionValue& Value)
{
	const FVector2D MoveVector = GetMovementInputScaleValue(Value.Get<FVector2D>());
	if (!GetController())
	{
		UE_LOG(LogTemp, Warning, TEXT("PlayerCharacter::Move(): Controller is nullptr"));
		return;
	}
	if (MoveVector.IsNearlyZero() || MoveVector.IsZero())
	{
		UE_LOG(LogTemp, Warning, TEXT("PlayerCharacter::Move(): Move vector is zero"));
		return;
	}
	// 获取控制器的旋转
	const FRotator ControllerRotation = GetController()->GetControlRotation();
	const FRotator ControllerYawRotation = FRotator(0.f, ControllerRotation.Yaw, 0.f);
	// 计算前进方向和右方向
	const FVector ForwardDirection = FRotationMatrix(ControllerYawRotation).GetUnitAxis(EAxis::X);
	const FVector RightDirection = FRotationMatrix(ControllerYawRotation).GetUnitAxis(EAxis::Y);
	// 添加移动输入
	AddMovementInput(ForwardDirection, MoveVector.Y);
	AddMovementInput(RightDirection, MoveVector.X);
}

void APlayerCharacter::Move_WorldSpace(const FInputActionValue& Value)
{
	const FVector2D MoveVector = Value.Get<FVector2D>();
	if (!GetController())
	{
		UE_LOG(LogTemp,Warning,TEXT("PlayerCharacter::Move(): Controller is nullptr"));
		return;
	}
	if (MoveVector.IsNearlyZero()||MoveVector.IsZero())
	{
		UE_LOG(LogTemp,Warning,TEXT("PlayerCharacter::Move(): Move vector is zero"));
		return;
	}
	// 添加移动输入
	AddMovementInput(FVector{0.0f,1.0f,0.0f},MoveVector.GetSafeNormal().X);
	AddMovementInput(FVector{1.0f,0.0f,0.0f},MoveVector.GetSafeNormal().Y);
}

void APlayerCharacter::Look(const FInputActionValue& Value)
{
	const FVector2D LookVector = Value.Get<FVector2D>();
	if (!GetController())
	{
		UE_LOG(LogTemp, Warning, TEXT("PlayerCharacter::Look(): Controller is nullptr"));
		return;
	}
	if (LookVector.IsNearlyZero() || LookVector.IsZero())
	{
		UE_LOG(LogTemp,Warning,TEXT("PlayerCharacter::Look(): Look vector is zero"));
		return;
	}
	AddControllerYawInput(LookVector.X);
	AddControllerPitchInput(LookVector.Y);
}

void APlayerCharacter::Look_Gamepad(const FInputActionValue& Value)
{
	const FVector2D LookVector = UKismetMathLibrary::Multiply_Vector2DFloat
		(Value.Get<FVector2D>(), GetWorld()->GetDeltaSeconds());
	if (!GetController())
	{
		UE_LOG(LogTemp, Warning, TEXT("PlayerCharacter::Look_Gamepad(): Controller is nullptr"));
		return;
	}
	if (LookVector.IsNearlyZero() || LookVector.IsZero())
	{
		UE_LOG(LogTemp, Warning, TEXT("PlayerCharacter::Look_Gamepad(): Look vector is zero"));
		return;
	}
	AddControllerYawInput(LookVector.X);
	AddControllerPitchInput(LookVector.Y);
}

void APlayerCharacter::WalkToggle(const FInputActionValue& Value)
{
	// 步行和冲刺互斥，防止状态冲突
	if (!CharacterInputState.bWantsToSprint)
	{
		CharacterInputState.bWantsToWalk = !CharacterInputState.bWantsToWalk;
		UpdateCharacterInputState_Server(CharacterInputState);
	}
}

void APlayerCharacter::SprintToggle(const FInputActionValue& Value)
{
	bool bIsSprinting = Value.Get<bool>();
	CharacterInputState.bWantsToSprint = bIsSprinting;
	CharacterInputState.bWantsToWalk = false;
	UpdateCharacterInputState_Server(CharacterInputState);
}

void APlayerCharacter::CrouchToggle(const FInputActionValue& Value)
{
	if (GetCharacterMovement()->IsFalling())
	{
		return;
	}
	if (IsCrouched())
	{
		UnCrouch();
	}
	else
	{
		Crouch();
	}
}

void APlayerCharacter::StrafeToggle(const FInputActionValue& Value)
{
	CharacterInputState.bWantsToStrafe = !CharacterInputState.bWantsToStrafe;
	UpdateCharacterInputState_Server(CharacterInputState);
}

void APlayerCharacter::AimToggle(const FInputActionValue& Value)
{
	bool bIsAiming = Value.Get<bool>();
	CharacterInputState.bWantsToAim = bIsAiming;
	UpdateCharacterInputState_Server(CharacterInputState);
}

void APlayerCharacter::CameraSwitch(const FInputActionValue& Value)
{
	int8 CameraStyleNum = UKismetMathLibrary::Conv_ByteToInt(CameraStyle);
	CameraStyleNum++;
	if (CameraStyleNum > 3)
	{
		CameraStyleNum = 0;
	}

	CameraStyle = static_cast<ECameraStyle>(CameraStyleNum);
	UE_LOG(LogTemp, Warning, TEXT("CameraStyle changed to %d"), CameraStyleNum);
}
