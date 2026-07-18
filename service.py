import win32service
import win32serviceutil
import win32event
import servicemanager
import sys
import os
from pathlib import Path

# Add current directory to path to import app
sys.path.insert(0, str(Path(__file__).parent))


class TaskDingTalkService(win32serviceutil.ServiceFramework):
    _svc_name_ = "TaskDingTalkScheduler"
    _svc_display_name_ = "Task DingTalk Scheduler"
    _svc_description_ = "Flask app untuk schedule DingTalk dengan background scheduler"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.is_alive = True

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self.is_alive = False
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STOPPED,
            (self._svc_name_, '')
        )

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        self.main()

    def main(self):
        # Import app here to avoid issues during service installation
        from app import app, scheduler
        
        # Run Flask app in a non-blocking way
        # We'll run it in a separate thread
        import threading
        
        def run_flask():
            app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
        
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        # Wait for stop signal
        win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)
        
        # Shutdown scheduler
        scheduler.shutdown()
        flask_thread.join(timeout=5)


if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(TaskDingTalkService)
