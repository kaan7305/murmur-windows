# Defaults into docs\ because .gitignore drops _*.png, so the old default
# produced a screenshot the README could never show. A relative path is taken
# as relative to this script rather than to wherever the caller happens to be
# standing, so the documented path always means the same file in the repo.
param([string]$Out = "docs\screenshot.png")
if (-not [System.IO.Path]::IsPathRooted($Out)) { $Out = Join-Path $PSScriptRoot $Out }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Out) | Out-Null
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class Cap {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool EnumWindows(Proc p, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr h, uint cmd);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  public delegate bool Proc(IntPtr h, IntPtr l);
  // Biggest window wins, because Murmur holds the recording overlay and the
  // main window open at the same time and Qt titles both of them "Murmur".
  // The overlay is a small always-on-top pill and therefore comes first in the
  // z-order, so MainWindowHandle, which takes the first one it enumerates,
  // yields a 102x56 crop instead of the app. Owned windows are skipped to keep
  // Qt's invisible IME and message-only helpers out of the running.
  public static IntPtr Find(uint pid, string title) {
    IntPtr best = IntPtr.Zero;
    long bestArea = -1;
    EnumWindows(delegate(IntPtr h, IntPtr l) {
      uint owner;
      GetWindowThreadProcessId(h, out owner);
      if (owner != pid || GetWindow(h, 4) != IntPtr.Zero) return true;
      StringBuilder text = new StringBuilder(256);
      GetWindowTextW(h, text, 256);
      if (text.ToString() != title) return true;
      RECT r;
      GetWindowRect(h, out r);
      long area = (long)(r.R - r.L) * (r.B - r.T);
      if (area > bestArea) { bestArea = area; best = h; }
      return true;
    }, IntPtr.Zero);
    return best;
  }
}
"@
# Before any window is measured. PowerShell is not DPI-aware by default, so on a
# scaled display GetWindowRect hands back virtualised coordinates - two thirds of
# the real size at 150% - while PrintWindow still renders the window at its true
# pixel size. The bitmap then comes out too small and the right and bottom edges
# are silently cropped, which is how the first README screenshot lost a column.
[Cap]::SetProcessDPIAware() | Out-Null

# Murmur is "python" from source (run.bat starts it that way) and "Murmur"
# once PyInstaller freezes it. Matching only python meant this failed against
# the installed build, which is the one worth screenshotting. The title match
# stays exact so the setup wizard, "Murmur setup", is never captured instead.
$h = [IntPtr]::Zero
foreach ($p in Get-Process -Name python, Murmur -ErrorAction SilentlyContinue) {
  $h = [Cap]::Find([uint32]$p.Id, "Murmur")
  if ($h -ne [IntPtr]::Zero) { break }
}
if ($h -eq [IntPtr]::Zero) { "no Murmur window"; exit 1 }
[Cap]::ShowWindow($h, 9) | Out-Null
Start-Sleep -Milliseconds 800
$r = New-Object Cap+RECT
[Cap]::GetWindowRect($h, [ref]$r) | Out-Null
$bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
[Cap]::PrintWindow($h, $hdc, 2) | Out-Null
$g.ReleaseHdc($hdc)
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
"captured $Out"
