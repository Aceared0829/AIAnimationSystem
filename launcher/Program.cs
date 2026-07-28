using System.Diagnostics;
using System.Windows.Forms;

namespace MotionBricksLauncher;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        string projectRoot = Path.GetDirectoryName(Environment.ProcessPath) ?? AppContext.BaseDirectory;
        string logPath = Path.Combine(projectRoot, "MotionBricks-launcher.log");
        string pythonw = Path.Combine(projectRoot, ".venv", "Scripts", "pythonw.exe");
        string workingDirectory = Path.Combine(projectRoot, "motionbricks");
        string demoScript = Path.Combine(workingDirectory, "scripts", "interactive_demo_g1.py");

        if (!File.Exists(pythonw) || !File.Exists(demoScript))
        {
            File.AppendAllText(
                logPath,
                $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} 未找到运行环境。pythonw={pythonw}; script={demoScript}{Environment.NewLine}"
            );
            MessageBox.Show(
                "未找到 MotionBricks 运行环境。\n\n请确保启动器位于项目根目录，且 .venv 已正确安装。",
                "MotionBricks 启动失败",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return;
        }

        try
        {
            Process? process = Process.Start(new ProcessStartInfo
            {
                FileName = pythonw,
                Arguments = $"\"{demoScript}\" --chinese_ui 1",
                WorkingDirectory = workingDirectory,
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden,
            });
            File.AppendAllText(
                logPath,
                $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} 已启动 MotionBricks，PID={process?.Id}{Environment.NewLine}"
            );
        }
        catch (Exception exception)
        {
            File.AppendAllText(
                logPath,
                $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} 启动失败：{exception}{Environment.NewLine}"
            );
            MessageBox.Show(
                $"无法启动 MotionBricks：\n\n{exception.Message}",
                "MotionBricks 启动失败",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
        }
    }
}
