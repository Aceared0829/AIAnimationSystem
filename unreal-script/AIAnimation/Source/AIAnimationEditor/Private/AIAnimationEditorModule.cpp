// Copyright ZhaoZining. All Rights Reserved.

// 编辑器工作台、动画图节点与模型导入工具只在编辑器宿主中加载。
#include "AIAnimationWorkbench.h"
#include "Framework/Docking/TabManager.h"
#include "Framework/Application/SlateApplication.h"
#include "HAL/IConsoleManager.h"
#include "Interfaces/IMainFrameModule.h"
#include "Modules/ModuleManager.h"
#include "Styling/AppStyle.h"
#include "ToolMenus.h"
#include "Widgets/Docking/SDockTab.h"
#include "Widgets/SWindow.h"

#define LOCTEXT_NAMESPACE "AIAnimationEditor"

namespace
{
	const FName WorkbenchTabId(TEXT("AIAnimationWorkbench"));
}

class FAIAnimationEditorModule final : public IModuleInterface
{
public:
	virtual void StartupModule() override
	{
		if (IsRunningCommandlet())
		{
			return;
		}
		FGlobalTabmanager::Get()->RegisterNomadTabSpawner(WorkbenchTabId, FOnSpawnTab::CreateRaw(this, &FAIAnimationEditorModule::SpawnWorkbench))
			.SetDisplayName(LOCTEXT("WorkbenchTitle", "AIAnimation 预览工作台"))
			.SetTooltipText(LOCTEXT("WorkbenchTooltip", "选择动画并编辑硬姿态参考"))
			.SetIcon(FSlateIcon(FAppStyle::GetAppStyleSetName(), "LevelEditor.Tabs.Viewports"));
		UToolMenus::RegisterStartupCallback(FSimpleMulticastDelegate::FDelegate::CreateRaw(this, &FAIAnimationEditorModule::RegisterMenus));
		OpenCommand = IConsoleManager::Get().RegisterConsoleCommand(TEXT("AIAnimation.OpenWorkbench"), TEXT("打开 AIAnimation 编辑器预览工作台。"),
			FConsoleCommandDelegate::CreateLambda([] { FGlobalTabmanager::Get()->TryInvokeTab(WorkbenchTabId); }), ECVF_Default);
		StandaloneCommand = IConsoleManager::Get().RegisterConsoleCommand(TEXT("AIAnimation.OpenWorkbenchOnly"), TEXT("只显示 AIAnimation 推理预览窗口。"),
			FConsoleCommandDelegate::CreateRaw(this, &FAIAnimationEditorModule::OpenStandaloneWorkbench), ECVF_Default);
	}

	virtual void ShutdownModule() override
	{
		if (IsRunningCommandlet())
		{
			return;
		}
		if (TSharedPtr<SWindow> Window = StandaloneWindow.Pin())
		{
			Window->SetOnWindowClosed(FOnWindowClosed());
			Window->RequestDestroyWindow();
		}
		StandaloneWindow.Reset();
		UToolMenus::UnRegisterStartupCallback(this);
		if (UToolMenus* Menus = UToolMenus::TryGet())
		{
			Menus->UnregisterOwner(this);
		}
		FGlobalTabmanager::Get()->UnregisterNomadTabSpawner(WorkbenchTabId);
		if (OpenCommand)
		{
			IConsoleManager::Get().UnregisterConsoleObject(OpenCommand);
			OpenCommand = nullptr;
		}
		if (StandaloneCommand)
		{
			IConsoleManager::Get().UnregisterConsoleObject(StandaloneCommand);
			StandaloneCommand = nullptr;
		}
	}

private:
	IConsoleObject* OpenCommand = nullptr;
	IConsoleObject* StandaloneCommand = nullptr;
	TWeakPtr<SWindow> StandaloneWindow;

	void OpenStandaloneWorkbench()
	{
		if (TSharedPtr<SWindow> Existing = StandaloneWindow.Pin())
		{
			Existing->BringToFront();
			return;
		}
		TSharedRef<SWindow> Window = SNew(SWindow)
			.Title(LOCTEXT("StandaloneTitle", "AIAnimation · 推理预览工作台"))
			.ClientSize(FVector2D(1920.0f, 1080.0f))
			.SizingRule(ESizingRule::UserSized)
			.SupportsMaximize(true)
			.SupportsMinimize(true);
		Window->SetContent(CreateAIAnimationWorkbench());
		Window->SetOnWindowClosed(FOnWindowClosed::CreateRaw(this, &FAIAnimationEditorModule::OnStandaloneClosed));
		StandaloneWindow = Window;
		FSlateApplication::Get().AddWindow(Window);
		if (TSharedPtr<SWindow> MainWindow = IMainFrameModule::Get().GetParentWindow())
		{
			MainWindow->HideWindow();
		}
		Window->Maximize();
	}

	void OnStandaloneClosed(const TSharedRef<SWindow>& Window)
	{
		StandaloneWindow.Reset();
		if (TSharedPtr<SWindow> MainWindow = IMainFrameModule::Get().GetParentWindow())
		{
			MainWindow->ShowWindow();
		}
		IMainFrameModule::Get().RequestCloseEditor();
	}

	TSharedRef<SDockTab> SpawnWorkbench(const FSpawnTabArgs& Args)
	{
		return SNew(SDockTab).TabRole(ETabRole::NomadTab)[CreateAIAnimationWorkbench()];
	}

	void RegisterMenus()
	{
		FToolMenuOwnerScoped Owner(this);
		UToolMenu* Menu = UToolMenus::Get()->ExtendMenu(TEXT("LevelEditor.MainMenu.Tools"));
		FToolMenuSection& Section = Menu->FindOrAddSection(TEXT("AIAnimation"));
		Section.AddMenuEntry(TEXT("OpenAIAnimationWorkbench"), LOCTEXT("OpenWorkbench", "AIAnimation 预览工作台"),
			LOCTEXT("OpenWorkbenchTooltip", "打开动画推理与硬姿态参考预览工作台"), FSlateIcon(),
			FUIAction(FExecuteAction::CreateLambda([] { FGlobalTabmanager::Get()->TryInvokeTab(WorkbenchTabId); })));
	}
};

IMPLEMENT_MODULE(FAIAnimationEditorModule, AIAnimationEditor)

#undef LOCTEXT_NAMESPACE
