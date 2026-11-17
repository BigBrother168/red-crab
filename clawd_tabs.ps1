# clawd_tabs.ps1: the tabs of a Windows Terminal window, for the conversations' circles (clawd_pet.pyw runs it).
#   selected <hwnd>        -> prints the internal id (UI Automation RuntimeId) of the tab selected in that window
#   select <hwnd> <id>     -> selects the tab with that id; prints "ok" or "gone"
# A tab's id stays the same while the tab is open, whatever its title becomes (a rename, the program's own title).
# Only reads and selects tabs; nothing in them is read.
# "gone" only after a second look: while the window is being switched about (quick clicks on two circles), its list
# of tabs can come back without the one there (2026-11-13: a tab still open was taken for closed).
param([string]$mode, [long]$hwnd, [string]$rid)
try {
    Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
    $w = [Windows.Automation.AutomationElement]::FromHandle([IntPtr]$hwnd)
    $cond = New-Object Windows.Automation.PropertyCondition(
        [Windows.Automation.AutomationElementIdentifiers]::ControlTypeProperty, [Windows.Automation.ControlType]::TabItem)
    $pat = [Windows.Automation.SelectionItemPatternIdentifiers]::Pattern
    foreach ($try in 1, 2) {
        foreach ($t in $w.FindAll([Windows.Automation.TreeScope]::Descendants, $cond)) {
            $id = [string]::Join('.', $t.GetRuntimeId())
            if ($mode -eq 'selected' -and $t.GetCurrentPattern($pat).Current.IsSelected) { $id; exit 0 }
            if ($mode -eq 'select' -and $id -eq $rid) { $t.GetCurrentPattern($pat).Select(); 'ok'; exit 0 }
        }
        if ($try -eq 1) { Start-Sleep -Milliseconds 300 }
    }
    if ($mode -eq 'select') { 'gone' }
} catch { 'error' }
