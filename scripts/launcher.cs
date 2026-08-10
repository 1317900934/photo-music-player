// Music Album Player - portable launcher
// A tiny Windows GUI launcher that starts the app with the bundled
// Python runtime (no console window). Also forwards a .pmb file path
// when opened via file association.
using System;
using System.Diagnostics;
using System.IO;

public static class MusicAlbumLauncher
{
    [STAThread]
    public static int Main(string[] args)
    {
        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        string pythonw = Path.Combine(baseDir, "runtime", "python", "pythonw.exe");
        if (!File.Exists(pythonw))
            pythonw = Path.Combine(baseDir, "runtime", "python", "python.exe");
        string script = Path.Combine(baseDir, "main.py");
        if (!File.Exists(pythonw) || !File.Exists(script))
        {
            System.Windows.Forms.MessageBox.Show(
                "Cannot find the bundled runtime.\nPlease keep the program folder complete.",
                "Music Album Player",
                System.Windows.Forms.MessageBoxButtons.OK,
                System.Windows.Forms.MessageBoxIcon.Error);
            return 1;
        }
        ProcessStartInfo psi = new ProcessStartInfo();
        psi.FileName = pythonw;
        psi.WorkingDirectory = baseDir;
        string arg = "\"" + script + "\"";
        if (args != null && args.Length > 0)
            arg += " \"" + args[0] + "\"";
        psi.Arguments = arg;
        psi.UseShellExecute = false;
        try
        {
            Process.Start(psi);
        }
        catch (Exception ex)
        {
            System.Windows.Forms.MessageBox.Show(
                "Failed to start the app: " + ex.Message,
                "Music Album Player",
                System.Windows.Forms.MessageBoxButtons.OK,
                System.Windows.Forms.MessageBoxIcon.Error);
            return 1;
        }
        return 0;
    }
}
