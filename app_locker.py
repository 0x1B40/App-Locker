import tkinter as tk
from tkinter import messagebox, ttk
import sqlite3
import os
import datetime
import pystray
from PIL import Image
import psutil
from threading import Thread
import winreg
import sys
import ctypes

class AppLocker:
    def __init__(self):
        try:
            # Initialize database connection for main thread
            self.conn = sqlite3.connect('app_locker.db', check_same_thread=False)
            self.create_db()
            
            # Initialize main window
            self.root = tk.Tk()
            self.root.title("App Locker")
            self.root.geometry("600x400")
            
            # System tray
            self.icon = None
            self.create_system_tray()
            
            # Setup GUI
            self.setup_gui()
            
            # Start monitoring thread
            self.running = True
            self.monitor_thread = Thread(target=self.monitor_apps)
            self.monitor_thread.daemon = True
            self.monitor_thread.start()
            
        except Exception as e:
            with open("app_locker_log.txt", "a", buffering=1) as log_file:
                log_file.write(f"[{datetime.datetime.now()}] Init error: {str(e)}\n")
            messagebox.showerror("Error", f"Initialization failed: {str(e)}")
            sys.exit(1)

    def create_db(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS app_rules (
                id INTEGER PRIMARY KEY,
                app_path TEXT NOT NULL,
                app_name TEXT NOT NULL,
                monday INTEGER,
                tuesday INTEGER,
                wednesday INTEGER,
                thursday INTEGER,
                friday INTEGER,
                saturday INTEGER,
                sunday INTEGER
            )
        ''')
        self.conn.commit()

    def setup_gui(self):
        tk.Label(self.root, text="Select Application:").pack(pady=5)
        
        self.app_entry = tk.Entry(self.root, width=50)
        self.app_entry.pack(pady=5)
        
        tk.Button(self.root, text="Browse", command=self.browse_app).pack(pady=5)
        
        tk.Label(self.root, text="Allowed Days:").pack(pady=5)
        
        self.days_vars = {}
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        for day in days:
            var = tk.BooleanVar()
            self.days_vars[day.lower()] = var
            tk.Checkbutton(self.root, text=day, variable=var).pack()
        
        tk.Button(self.root, text="Add Rule", command=self.add_rule).pack(pady=10)
        
        self.tree = ttk.Treeview(self.root, columns=('App', 'Days'), show='headings')
        self.tree.heading('App', text='Application')
        self.tree.heading('Days', text='Allowed Days')
        self.tree.pack(fill='both', expand=True, padx=10, pady=10)
        
        tk.Button(self.root, text="Delete Selected Rule", command=self.delete_rule).pack(pady=5)
        
        self.update_rules_list()

    def browse_app(self):
        from tkinter import filedialog
        app_path = filedialog.askopenfilename(filetypes=[("Executable files", "*.exe")])
        if app_path:
            self.app_entry.delete(0, tk.END)
            self.app_entry.insert(0, app_path)

    def add_rule(self):
        app_path = self.app_entry.get()
        if not app_path or not os.path.exists(app_path):
            messagebox.showerror("Error", "Please select a valid application")
            return
            
        app_name = os.path.basename(app_path)
        days = {day: 1 if var.get() else 0 for day, var in self.days_vars.items()}
        
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO app_rules 
            (app_path, app_name, monday, tuesday, wednesday, thursday, friday, saturday, sunday)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            app_path, app_name, 
            days['monday'], days['tuesday'], days['wednesday'], 
            days['thursday'], days['friday'], days['saturday'], days['sunday']
        ))
        self.conn.commit()
        
        self.update_rules_list()
        messagebox.showinfo("Success", "Rule added successfully")

    def update_rules_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM app_rules")
        for row in cursor.fetchall():
            allowed_days = []
            for i, day in enumerate(['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']):
                if row[3+i] == 1:
                    allowed_days.append(day.capitalize())
            days_str = ", ".join(allowed_days) if allowed_days else "None"
            self.tree.insert('', 'end', values=(row[2], days_str))

    def delete_rule(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showerror("Error", "Please select a rule to delete")
            return
            
        app_name = self.tree.item(selected[0])['values'][0]
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM app_rules WHERE app_name = ?", (app_name,))
        self.conn.commit()
        
        self.update_rules_list()
        messagebox.showinfo("Success", "Rule deleted successfully")

    def create_system_tray(self):
        image = Image.new('RGB', (64, 64), color='blue')
        menu = pystray.Menu(
            pystray.MenuItem("Show", self.show_window),
            pystray.MenuItem("Exit", self.quit)
        )
        self.icon = pystray.Icon("App Locker", image, "App Locker", menu)
        Thread(target=self.icon.run, daemon=True).start()

    def show_window(self):
        self.root.deiconify()

    def monitor_apps(self):
        try:
            # Log thread start
            with open("app_locker_log.txt", "a", buffering=1) as log_file:
                log_file.write(f"[{datetime.datetime.now()}] Monitor thread started\n")
            
            # Create SQLite connection for this thread
            conn = sqlite3.connect('app_locker.db', check_same_thread=False)
            
            while self.running:
                try:
                    current_day = datetime.datetime.now().strftime('%A').lower()
                    with open("app_locker_log.txt", "a", buffering=1) as log_file:
                        log_file.write(f"[{datetime.datetime.now()}] Checking for {current_day}\n")
                    
                    cursor = conn.cursor()
                    cursor.execute("SELECT app_path, app_name, " + current_day + " FROM app_rules")
                    rules = cursor.fetchall()
                    with open("app_locker_log.txt", "a", buffering=1) as log_file:
                        log_file.write(f"[{datetime.datetime.now()}] Rules loaded: {rules}\n")
                    
                    for proc in psutil.process_iter(['name', 'exe']):
                        try:
                            proc_name = proc.info['name'].lower() if proc.info['name'] else ""
                            proc_path = proc.info['exe'] if proc.info['exe'] else ""
                            # Normalize names and paths
                            proc_name_normalized = proc_name.replace(" ", "")
                            proc_path_normalized = os.path.normcase(proc_path) if proc_path else ""
                            with open("app_locker_log.txt", "a", buffering=1) as log_file:
                                log_file.write(f"[{datetime.datetime.now()}] Checking process: {proc_name}, {proc_path}\n")
                            
                            for rule in rules:
                                rule_name = rule[1].lower()
                                rule_path = os.path.normcase(rule[0].replace("/", "\\"))
                                rule_name_normalized = rule_name.replace(" ", "")
                                # Match by name or path
                                if (proc_name_normalized == rule_name_normalized or 
                                    (proc_path_normalized and proc_path_normalized == rule_path)) and rule[2] == 0:
                                    with open("app_locker_log.txt", "a", buffering=1) as log_file:
                                        log_file.write(f"[{datetime.datetime.now()}] Restricted app detected: {proc_name} (normalized: {proc_name_normalized}, path: {proc_path_normalized})\n")
                                    try:
                                        psutil.Process(proc.pid).terminate()
                                        self.root.after(0, lambda: messagebox.showwarning(
                                            "Restricted", f"{proc_name} is not allowed to run on {current_day.capitalize()}"
                                        ))
                                    except psutil.AccessDenied:
                                        with open("app_locker_log.txt", "a", buffering=1) as log_file:
                                            log_file.write(f"[{datetime.datetime.now()}] Access denied for {proc_name}\n")
                                        self.root.after(0, lambda: messagebox.showerror(
                                            "Error", f"Access denied when terminating {proc_name}. Run as administrator."
                                        ))
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                    
                    conn.commit()
                except Exception as e:
                    with open("app_locker_log.txt", "a", buffering=1) as log_file:
                        log_file.write(f"[{datetime.datetime.now()}] Error in monitor loop: {str(e)}\n")
                    self.root.after(0, lambda: messagebox.showerror("Error", f"Monitoring error: {str(e)}"))
                
                import time
                time.sleep(1)
            
            with open("app_locker_log.txt", "a", buffering=1) as log_file:
                log_file.write(f"[{datetime.datetime.now()}] Monitor thread stopped\n")
            conn.close()
            
        except Exception as e:
            with open("app_locker_log.txt", "a", buffering=1) as log_file:
                log_file.write(f"[{datetime.datetime.now()}] Monitor thread error: {str(e)}\n")
            self.root.after(0, lambda: messagebox.showerror("Error", f"Monitor thread failed: {str(e)}"))

    def quit(self):
        self.running = False
        if self.icon:
            self.icon.stop()
        self.conn.close()
        self.root.destroy()
        sys.exit()

    def run(self):
        self.root.mainloop()

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if __name__ == "__main__":
    if not is_admin():
        messagebox.showwarning("Warning", "App Locker requires administrator privileges to terminate processes. Please run as administrator.")
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)
        sys.exit()
    
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                            r"Software\Microsoft\Windows\CurrentVersion\Run", 
                            0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "AppLocker", 0, winreg.REG_SZ, f'"{sys.executable}" "{os.path.abspath(__file__)}"')
        winreg.CloseKey(key)
    except WindowsError:
        pass
        
    app = AppLocker()
    app.run()