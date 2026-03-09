# How to Configure Windows Scheduled Task with Administrator Privileges

## Problem
When running `auto_update_all_tables.bat` via Windows Task Scheduler, you see:
```
[WARNING] Administrator privileges not detected
[WARNING] Service control requires administrator privileges
[WARNING] Update may fail if backend service is running
```

This means the task is not running with administrator privileges, so it cannot stop/start the TR-Backend service.

## Solution: Configure Task to Run with Highest Privileges

### Method 1: Using Task Scheduler GUI (Recommended)

1. **Open Task Scheduler**
   - Press `Win + R`, type `taskschd.msc`, press Enter
   - Or: Control Panel → Administrative Tools → Task Scheduler

2. **Find Your Task**
   - In the left panel, navigate to "Task Scheduler Library"
   - Find your task (e.g., `TR_Database_Auto_Update` or `auto_update_all_tables`)

3. **Open Task Properties**
   - Right-click the task → **Properties** (or double-click)

4. **Enable Highest Privileges**
   - Go to **"General"** tab
   - **Check the box**: ✅ **"Run with highest privileges"**
   - This is the most important setting!

5. **Configure Other Settings**
   - **Run whether user is logged on or not**: Select this if you want the task to run even when no one is logged in
   - **Run only when user is logged on**: Select this if you want the task to run only when the user is logged in
   - **Hidden**: Optional, check if you don't want the task window to be visible

6. **Configure Action (if not already set)**
   - Go to **"Actions"** tab
   - Select the action → **Edit**
   - **Program/script**:
     ```
     C:\TR-master\TR database\auto_update_all_tables.bat
     ```
   - **Add arguments (optional)**:
     ```
     /NO_PAUSE
     ```
   - **Start in (optional)**:
     ```
     C:\TR-master\TR database
     ```

7. **Save**
   - Click **OK** → Enter password if prompted → **OK**

### Method 2: Using Command Line (schtasks)

#### Modify Existing Task to Run with Highest Privileges

Run PowerShell or CMD **as Administrator**, then execute:

```batch
schtasks /change /tn "TR_Database_Auto_Update" /rl HIGHEST
```

#### Create New Task with Highest Privileges

```batch
schtasks /create ^
    /tn "TR_Database_Auto_Update" ^
    /tr "\"C:\TR-master\TR database\auto_update_all_tables.bat\" /NO_PAUSE" ^
    /sc DAILY ^
    /st 06:30 ^
    /ru "%USERNAME%" ^
    /rl HIGHEST ^
    /f
```

**Key Parameter:**
- `/rl HIGHEST` - Run with highest privileges (Administrator)

### Method 3: Verify Current Task Configuration

Check if your task is configured with highest privileges:

```batch
schtasks /query /tn "TR_Database_Auto_Update" /fo LIST /v | findstr "Run Level"
```

You should see:
```
Run Level:              Highest Available
```

If you see "Limited" or "Least Privilege", the task is not running with admin rights.

## Important Notes

### 1. User Account Requirements
- The user account running the task must have:
  - Administrator privileges on the local machine
  - Permission to control Windows services (TR-Backend)
  - Access to the database directory

### 2. Password Required
- If "Run whether user is logged on or not" is selected, you **must** provide the user's password
- The password is stored encrypted in Windows Task Scheduler

### 3. Service Control
- With highest privileges enabled, the batch script can:
  - Stop the TR-Backend service before database update
  - Start the TR-Backend service after database update
  - This prevents "database read-only" errors

### 4. Security Consideration
- Running with highest privileges means the task has full administrator access
- Only use this for trusted scripts
- Ensure the batch file and Python script are secure

## Troubleshooting

### Task Still Shows "Administrator privileges not detected"

1. **Verify Task Configuration**
   ```batch
   schtasks /query /tn "TR_Database_Auto_Update" /fo LIST /v
   ```
   Check "Run Level" should be "Highest Available"

2. **Recreate Task**
   - Delete the existing task
   - Create a new one with `/rl HIGHEST` parameter

3. **Check User Account**
   - Ensure the user account is in the Administrators group
   - Verify the user can manually stop/start services

### Task Fails to Start

1. **Check Task History**
   - Open Task Scheduler
   - Find your task → Click "History" tab
   - Look for error messages

2. **Test Manually**
   - Right-click task → **Run**
   - Check if it executes successfully

3. **Check Logs**
   - Review log files in: `C:\TR-master\TR database\logs\`
   - Look for error messages

### Service Control Still Fails

1. **Verify Service Name**
   - Ensure service name is correct: `TR-Backend`
   - Check: `sc query TR-Backend`

2. **Test Service Control Manually**
   - Run PowerShell as Administrator
   - Test: `Stop-Service TR-Backend`
   - Test: `Start-Service TR-Backend`

3. **Check Service Permissions**
   - Ensure the user account has permission to control the service
   - You may need to grant specific permissions to the service

## Quick Fix Command

If you want to quickly fix an existing task, run this in PowerShell **as Administrator**:

```powershell
# Change task to run with highest privileges
schtasks /change /tn "TR_Database_Auto_Update" /rl HIGHEST

# Verify the change
schtasks /query /tn "TR_Database_Auto_Update" /fo LIST /v | Select-String "Run Level"
```

## Summary

**The key setting is:**
- ✅ **"Run with highest privileges"** in Task Scheduler GUI
- Or `/rl HIGHEST` parameter when using `schtasks` command

Once this is enabled, the batch script will detect administrator privileges and can control the TR-Backend service.
