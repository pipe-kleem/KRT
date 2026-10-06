import os
import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

class DailyCleanupTool:
    def __init__(self, root):
        self.root = root
        self.root.title("Workspace Cleanup Tool")
        self.root.geometry("750x500")

        self.target_dir = tk.StringVar(value=str(Path.home() / "Documents"))
        self.target_date = tk.StringVar(value=datetime.date.today().strftime("%Y-%m-%d"))

        top_frame = tk.Frame(root)
        top_frame.pack(pady=10, fill="x", padx=10)

        tk.Label(top_frame, text="Target Folder:").grid(row=0, column=0, sticky="w", pady=5)
        tk.Entry(top_frame, textvariable=self.target_dir, width=50).grid(row=0, column=1, padx=5, pady=5)
        tk.Button(top_frame, text="Browse", command=self.browse_folder).grid(row=0, column=2, padx=5, pady=5)

        tk.Label(top_frame, text="Target Date (YYYY-MM-DD):").grid(row=1, column=0, sticky="w", pady=5)
        tk.Entry(top_frame, textvariable=self.target_date, width=20).grid(row=1, column=1, sticky="w", padx=5, pady=5)

        tk.Button(root, text="Scan Files for Selected Date", command=self.scan_files).pack(pady=5)

        columns = ("Path", "Type", "Date")
        self.tree = ttk.Treeview(root, columns=columns, show="headings", selectmode="extended")
        for col in columns: self.tree.heading(col, text=col)
        self.tree.column("Path", width=500)
        self.tree.column("Type", width=80)
        self.tree.column("Date", width=120)
        self.tree.pack(expand=True, fill="both", padx=10)

        tk.Button(root, text="Delete Selected", command=self.delete_files, bg="#d9534f", fg="white").pack(pady=10)

    def browse_folder(self):
        if folder := filedialog.askdirectory(): 
            self.target_dir.set(folder)

    def scan_files(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        folder_path = Path(self.target_dir.get())
        
        if not folder_path.exists(): 
            return messagebox.showerror("Error", "Folder not found.")
        
        try:
            target_date_obj = datetime.datetime.strptime(self.target_date.get(), "%Y-%m-%d").date()
        except ValueError:
            return messagebox.showerror("Error", "Invalid date format. Please use YYYY-MM-DD.")

        try:
            for f in folder_path.rglob("*"): 
                if f.is_file():
                    mtime = datetime.date.fromtimestamp(f.stat().st_mtime)
                    if mtime == target_date_obj:
                        self.tree.insert("", "end", values=(str(f), f.suffix or "File", mtime.strftime("%Y-%m-%d")))
        except Exception as e: 
            messagebox.showwarning("Warning", f"Access error: {e}")

    def delete_files(self):
        if selected := self.tree.selection():
            if messagebox.askyesno("Confirm", f"Delete {len(selected)} files permanently?"):
                for item in selected:
                    try: 
                        os.remove(self.tree.item(item, "values")[0])
                        self.tree.delete(item)
                    except: pass
                messagebox.showinfo("Done", "Cleanup complete.")

if __name__ == "__main__":
    root = tk.Tk()
    DailyCleanupTool(root)
    root.mainloop()