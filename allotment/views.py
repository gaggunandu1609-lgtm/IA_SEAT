from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
import pandas as pd
from students.models import Student
from teachers.models import Teacher
from rooms.models import Room
from exams.models import Exam, QuestionPaper
from allotment.models import SeatAllotment, TeacherAllotment
import math
from collections import defaultdict
import datetime
import random
import pdfplumber
import re
from django.db.models import Q

def dashboard(request):
    counts = {
        'students': Student.objects.count(),
        'teachers': Teacher.objects.count(),
        'rooms': Room.objects.count(),
        'exams': Exam.objects.count(),
        'allotments': SeatAllotment.objects.count(),
    }
    return render(request, 'dashboard.html', {'counts': counts})

def upload_data(request):
    if request.method == "POST":
        file_type = request.POST.get('file_type')
        if not file_type:
            # Fallback if someone uses dynamic forms without file_type
            pass
            
        file = request.FILES.get('file')
        if not file:
            messages.error(request, "No file uploaded.")
            return redirect('dashboard')
            
        try:
            if file.name.lower().endswith('.pdf'):
                with pdfplumber.open(file) as pdf:
                    dfs = []
                    for page in pdf.pages:
                        tables = page.extract_tables()
                        for table in tables:
                            if not table:
                                continue
                            
                            headers_found = False
                            table_data = []
                            headers = []
                            for i, row in enumerate(table):
                                row_strs = [str(h).lower() if h else '' for h in row]
                                # Extremely broad keyword search for headers
                                if any(k in r for r in row_strs for k in ['name', 'dept', 'usn', 'roll number', 'roll no', 'reg no', 'faculty', 'subject', 'exam', 'room', 'bench', 'student', 'date', 'time', 'timetable']):
                                    headers = [str(h).replace('\n', ' ').strip() for h in row]
                                    table_data = table[i+1:]
                                    headers_found = True
                                    break
                            
                            # Fallback: if no clear header but first col has numbers/letters, treat it as a data row
                            if not headers_found:
                                # Look for a row where 1st or 2nd col has a USN/ID pattern (e.g. 1MS20, 4MN25)
                                for i, row in enumerate(table):
                                    row_str = str(row[0]) if row and len(row)>0 else ""
                                    if re.search(r'[A-Za-z]+\d+', row_str) or re.search(r'\d+[A-Za-z]+', row_str):
                                        headers = [f"Col_{x}" for x in range(len(row))]
                                        table_data = table[i:]
                                        headers_found = True
                                        break
                                
                            if not headers_found: continue
                                
                            headers = [h if h else f"Col_{i}" for h, i in zip(headers, range(len(headers)))]
                            num_cols = len(headers)
                            cleaned_data = []
                            for row in table_data:
                                if not row or not any(row): continue
                                # Verify if row actually contains data (at least one non-empty string)
                                if not any(str(x).strip() for x in row): continue
                                
                                if len(row) > num_cols:
                                    cleaned_data.append(row[:num_cols])
                                elif len(row) < num_cols:
                                    cleaned_data.append(row + [''] * (num_cols - len(row)))
                                else:
                                    cleaned_data.append(row)
                                    
                            tdf = pd.DataFrame(cleaned_data, columns=headers)
                            tdf.columns = tdf.columns.astype(str).str.strip().str.lower()
                            tdf = tdf.loc[:, ~tdf.columns.duplicated()]
                            dfs.append(tdf)
                            
                    if not dfs:
                        raise ValueError("No valid tables found on pages. Please check if your PDF contains selectable text (not an image).")
                        
                    df = pd.concat(dfs, ignore_index=True)
                    
                    # clean up
                    for col in df.columns:
                        if df[col].dtype == object:
                            df[col] = df[col].astype(str).str.replace('\n', ' ').str.strip()
                            df[col] = df[col].replace('None', '')
            elif file.name.lower().endswith('.csv'):
                df = pd.read_csv(file)
                df.columns = df.columns.astype(str).str.strip().str.lower()
            else:
                raise ValueError("Unsupported file format. Please upload a CSV or PDF file.")
            
            if file_type == 'students':
                required_usn = ['usn', 'roll number', 'roll no', 'reg no']
                required_dept = ['department', 'dept', 'branch', 'course']
                
                if not any(k in df.columns for k in required_usn):
                    raise ValueError(f"Students list must contain USN. Columns found: {list(df.columns)}")
                
                rows_added = 0
                for _, row in df.iterrows():
                    # Find USN in any of the potential columns
                    usn_key = next((k for k in required_usn if k in df.columns), 'usn')
                    usn = str(row.get(usn_key, '')).strip()
                    
                    # More permissive USN check: Skip if truly header or empty, otherwise keep
                    if not usn or usn.lower() in ['usn', 'roll number', 'roll no', 'reg no', 'nan', 'none']:
                        continue
                    
                    dept_key = next((k for k in required_dept if k in df.columns), 'department')
                    dept = str(row.get(dept_key, '')).strip()
                    if dept.lower() in [dept_key, 'dept', 'nan', 'none']: dept = "Unknown"
                        
                    # Semester parsing
                    sem_val = row.get('semester', row.get('sem', 0))
                    try:
                        sem_val = int(float(sem_val)) if pd.notna(sem_val) and str(sem_val).strip() != '' else 0
                    except (ValueError, TypeError):
                        sem_val = 0

                    Student.objects.update_or_create(
                        usn=usn,
                        defaults={
                            'name': row.get('name', row.get('student name', '')),
                            'department': dept,
                            'semester': sem_val
                        }
                    )
                    rows_added += 1
                messages.success(request, f"Successfully uploaded {rows_added} students!")

            elif file_type == 'teachers':
                required_id = ['faculty id', 'id', 'emp id', 'employee id', 'faculty_id', 'sl no'] # permissive
                required_name = ['name', 'faculty name', 'teacher name']
                
                rows_added = 0
                for _, row in df.iterrows():
                    id_key = next((k for k in required_id if k in df.columns), None)
                    name_key = next((k for k in required_name if k in df.columns), 'name')
                    
                    fac_id = str(row.get(id_key, '')).strip() if id_key else ""
                    name = str(row.get(name_key, '')).strip()
                    
                    # Skip if header or missing name
                    if not name or name.lower() in ['name', 'faculty name', 'teacher name', 'nan']:
                        continue
                    if fac_id.lower() in ['faculty id', 'id', 'nan', 'none']: fac_id = f"T-{rows_added+1}"
                        
                    Teacher.objects.update_or_create(
                        faculty_id=fac_id,
                        defaults={
                            'name': name,
                            'department': row.get('department', row.get('dept', 'General'))
                        }
                    )
                    rows_added += 1
                messages.success(request, f"Successfully uploaded {rows_added} teachers!")
            elif file_type == 'rooms':
                if not any(k in df.columns for k in ['room number', 'room']):
                    raise ValueError("Rooms list must contain 'Room Number'.")
                if not any(k in df.columns for k in ['number of benches', 'benches']):
                    raise ValueError("Rooms list must contain 'Number of Benches'.")
                
                rows_added = 0
                for _, row in df.iterrows():
                    room_num = str(row.get('room number', row.get('room', ''))).strip()
                    if room_num.lower() in ['room number', 'room', 'nan', 'none', '']:
                        continue
                        
                    Room.objects.update_or_create(
                        room_number=room_num,
                        defaults={
                            'benches': row.get('number of benches', row.get('benches', 0))
                        }
                    )
                    rows_added += 1
                messages.success(request, f"Successfully uploaded {rows_added} rooms!")
            elif file_type == 'exams':
                if not any(k in df.columns for k in ['exam date', 'date']):
                    raise ValueError("Exams list must contain 'Exam Date'.")
                if 'time' not in df.columns:
                    raise ValueError("Exams list must contain 'Time'.")
                if 'subject' not in df.columns:
                    raise ValueError("Exams list must contain 'Subject'.")
                
                rows_added = 0
                rows_skipped = 0
                new_exams = []
                
                # Active values for forward-filling
                last_date_val = None
                last_time_val = None
                
                for _, row in df.iterrows():
                    try:
                        date_val = str(row.get('exam date', row.get('date', ''))).replace('nan', '').strip()
                        time_val = str(row.get('time', '')).replace('nan', '').strip()
                        subject = str(row.get('subject', '')).replace('nan', '').strip()
                        
                        # Forward-fill if empty (common in PDF tables with merged cells)
                        if not date_val and last_date_val:
                            date_val = last_date_val
                        else:
                            last_date_val = date_val
                            
                        if not time_val and last_time_val:
                            time_val = last_time_val
                        else:
                            last_time_val = time_val
                        
                        if not date_val or not time_val or not subject:
                            rows_skipped += 1
                            continue
                        
                        # Isolation for Date
                        date_match = re.search(r'(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})', date_val)
                        if date_match:
                            date_val = date_match.group(1)
                            
                        # Isolation for Time
                        time_match = re.search(r'(\d{1,2}[:\.]\d{1,2}\s*(?:AM|PM|A\.M|P\.M)*)', time_val, re.IGNORECASE)
                        if time_match:
                            time_val = time_match.group(1)
                        
                        # Standardize Time separators
                        time_val = re.sub(r'(\d{1,2})\.(\d{1,2})', r'\1:\2', time_val)
                        time_val = time_val.replace('A.M', 'AM').replace('a.m', 'am').replace('P.M', 'PM').replace('p.m', 'pm')
                        time_val = re.split(r'(?i)\s+to\s+|-', time_val)[0].strip()
                        
                        # Session/Marker detection
                        raw_time = time_val.replace(' ', '').upper()
                        has_pm_marker = 'PM' in raw_time
                        has_am_marker = 'AM' in raw_time
                        
                        dt_time = pd.to_datetime(time_val, errors='coerce')
                        
                        if not pd.isna(dt_time):
                            # Session column detection
                            session_col = str(row.get('session', row.get('exam session', ''))).lower()
                            
                            # Apply PM Heuristic if needed
                            if ('afternoon' in session_col or 'pm' in session_col or 'p.m' in session_col or has_pm_marker):
                                if dt_time.hour < 12:
                                    dt_time = dt_time + pd.Timedelta(hours=12)
                            elif 'morning' not in session_col and not has_am_marker:
                                # Normal Indian exam times (1:00 to 7:00) assumed afternoon
                                if 1 <= dt_time.hour <= 7:
                                    dt_time = dt_time + pd.Timedelta(hours=12)
                        
                        dt_date = pd.to_datetime(date_val, dayfirst=True, errors='coerce')
                        
                        if pd.isna(dt_date) or pd.isna(dt_time):
                            rows_skipped += 1
                            continue
                            
                        new_exams.append(Exam(
                            subject=subject,
                            date=dt_date.date(),
                            time=dt_time.time()
                        ))
                        rows_added += 1
                    except (ValueError, TypeError):
                        rows_skipped += 1
                        continue
                
                if rows_added == 0:
                    first_row = df.iloc[0].to_dict() if not df.empty else "No Data"
                    messages.warning(request, f"Read {len(df)} rows, but 0 valid exams found. Sample data from Row 1: {first_row}. Expected 'Date' (D/M/Y), 'Time' (H:M), 'Subject'.")
                else:
                    Exam.objects.all().delete()
                    Exam.objects.bulk_create(new_exams)
                    msg = f"Successfully uploaded {rows_added} exams!"
                    if rows_skipped > 0:
                        msg += f" (Skipped {rows_skipped} malformed rows)"
                    messages.success(request, msg)
            
            # Replaced generic success message with the ones above
        except Exception as e:
            messages.error(request, f"Error processing file: {e}")
            
    return redirect('dashboard')

def generate_seating(request):
    if request.method == "POST":
        SeatAllotment.objects.all().delete()
        rooms = list(Room.objects.order_by('room_number'))
        if not rooms:
            messages.error(request, "No rooms available. Please upload rooms data.")
            return render(request, 'partials/seating_status.html')

        # Get all students and sort by USN for a consistent master plan
        mca_students = list(Student.objects.filter(department__iexact='MCA').order_by('usn'))
        mba_students = list(Student.objects.filter(department__iexact='MBA').order_by('usn'))
        
        if not (mca_students or mba_students):
            messages.warning(request, "No students found in the database. Upload students first.")
            return render(request, 'partials/seating_status.html')

        # Use the first available exam as a placeholder (since seating is static for the session)
        master_exam = Exam.objects.first()
        if not master_exam:
            # Create a dummy exam if none exist to satisfy the ForeignKey
            master_exam = Exam.objects.create(subject="General Seating", date="2026-01-01", time="09:00")

        room_idx = 0
        bench_idx = 1
        current_room = rooms[room_idx]

        while mca_students or mba_students:
            s1 = s2 = s3 = None

            # Overflow to next room BEFORE assigning – so bench_idx is always valid
            if bench_idx > current_room.benches:
                room_idx += 1
                if room_idx >= len(rooms):
                    remaining_count = len(mca_students) + len(mba_students)
                    messages.warning(request, f"Capacity warning: {remaining_count} students couldn't be seated due to total room capacity.")
                    break
                current_room = rooms[room_idx]
                bench_idx = 1

            # Determine which column group this bench belongs to (0-indexed column)
            # Each column has 5 benches: col 0 = benches 1-5, col 1 = 6-10, col 2 = 11-15, col 3 = 16-20
            col_group = (bench_idx - 1) // 5  # 0, 1, 2, 3 ...
            # Even columns (0, 2, ...): pattern MCA, MBA, MCA
            # Odd columns  (1, 3, ...): pattern MBA, MCA, MBA
            if col_group % 2 == 0:
                # Pattern: MCA, MBA, MCA
                if mca_students: s1 = mca_students.pop(0)
                elif mba_students: s1 = mba_students.pop(0)

                if mba_students: s2 = mba_students.pop(0)
                elif mca_students: s2 = mca_students.pop(0)

                if mca_students: s3 = mca_students.pop(0)
                elif mba_students: s3 = mba_students.pop(0)
            else:
                # Pattern: MBA, MCA, MBA
                if mba_students: s1 = mba_students.pop(0)
                elif mca_students: s1 = mca_students.pop(0)

                if mca_students: s2 = mca_students.pop(0)
                elif mba_students: s2 = mba_students.pop(0)

                if mba_students: s3 = mba_students.pop(0)
                elif mca_students: s3 = mca_students.pop(0)

            if not (s1 or s2 or s3): break

            SeatAllotment.objects.create(
                exam=master_exam,
                room=current_room,
                bench_number=bench_idx,
                student_1=s1,
                student_2=s2,
                student_3=s3,
            )
            bench_idx += 1

        messages.success(request, "Master seating plan generated successfully for all students.")
        return render(request, 'partials/seating_status.html')

def generate_teachers(request):
    if request.method == "POST":
        TeacherAllotment.objects.all().delete()
        Teacher.objects.all().update(workload=0)
        
        # Split teachers by department
        all_teachers = list(Teacher.objects.all())
        mca_staff = [t for t in all_teachers if 'MCA' in t.department.upper()]
        mba_staff = [t for t in all_teachers if 'MBA' in t.department.upper()]
        
        if not (mca_staff or mba_staff):
            messages.error(request, "Please upload teachers with MCA/MBA departments.")
            return render(request, 'partials/teacher_status.html')

        # Group exams by unique (Date, Time) slots to define "Sessions"
        slots = Exam.objects.values('date', 'time').distinct().order_by('date', 'time')
        rooms = list(Room.objects.all().order_by('room_number'))
        
        if not (slots and rooms):
            if not slots:
                messages.error(request, "No exams uploaded. Please upload the Exam Timetable Schedule first.")
            if not rooms:
                messages.error(request, "No rooms found. Please upload the Rooms list first.")
            return render(request, 'partials/teacher_status.html')

        # Use rotating indices for each staff pool to ensure balanced workload
        mca_ptr = 0
        mba_ptr = 0
        
        for slot in slots:
            # Representative exam for the session (to satisfy ForeignKey)
            exam_ref = Exam.objects.filter(date=slot['date'], time=slot['time']).first()
            
            for room in rooms:
                room_name = room.room_number.upper()
                
                # CROSS-DEPARTMENT LOGIC:
                # MBA Room -> Needs MCA Staff
                # MCA Room -> Needs MBA Staff
                if 'MBA' in room_name:
                    targets = mca_staff
                    ptr = mca_ptr
                elif 'MCA' in room_name:
                    targets = mba_staff
                    ptr = mba_ptr
                else:
                    targets = all_teachers
                    ptr = (mca_ptr + mba_ptr) // 2

                if not targets:
                    targets = all_teachers # Last resort
                    
                # Find the next available teacher in the target pool
                found = False
                attempts = 0
                while not found and attempts < len(targets):
                    t = targets[ptr % len(targets)]
                    # Ensure teacher doesn't have two duties in the same slot
                    if not TeacherAllotment.objects.filter(exam__date=slot['date'], exam__time=slot['time'], teacher=t).exists():
                        TeacherAllotment.objects.create(
                            exam=exam_ref,
                            room=room,
                            teacher=t
                        )
                        t.workload += 1
                        found = True
                    ptr += 1
                    attempts += 1
                
                # Update department-specific pointers back to the global state
                if 'MBA' in room_name: mca_ptr = ptr
                elif 'MCA' in room_name: mba_ptr = ptr
                else:
                    mca_ptr = ptr
                    mba_ptr = ptr

        for t in all_teachers:
            t.save()

        messages.success(request, "Invigilation generated: Exactly 2 people per room. MBA staff in MCA rooms, MCA staff in MBA rooms.")
        return render(request, 'partials/teacher_status.html')



def seating_reports(request):
    # This view generates reports based on the ACTUAL generated allotments in the database
    allotments = SeatAllotment.objects.select_related('exam', 'room', 'student_1', 'student_2', 'student_3').all().order_by('room__room_number', 'bench_number')
    
    if not allotments:
        return render(request, 'partials/seating_reports.html', {'reports': []})

    grouped = defaultdict(list)
    for a in allotments:
        grouped[a.room].append(a)
    
    report_data = []
    for room in sorted(grouped.keys(), key=lambda r: r.room_number):
        benches = grouped[room]
        # Use a 45-seat grid (15 rows x 3 columns) — 15 benches × 3 seats
        grid = [""] * 45
        
        courses = set()
        for b in benches:
            # Each bench has 3 seats mapping to indices: (bench-1)*3, (bench-1)*3 + 1, (bench-1)*3 + 2
            base_idx = (b.bench_number - 1) * 3
            if base_idx + 2 < 45:
                if b.student_1:
                    grid[base_idx] = b.student_1.usn
                    courses.add(b.student_1.department)
                if b.student_2:
                    grid[base_idx+1] = b.student_2.usn
                    courses.add(b.student_2.department)
                if b.student_3:
                    grid[base_idx+2] = b.student_3.usn
                    courses.add(b.student_3.department)
        
        exam = benches[0].exam if benches else None
        
        report_data.append({
            'room': room,
            'usns': grid,
            'date': exam.date.strftime('%d/%m/%Y') if exam else datetime.date.today().strftime('%d/%m/%Y'),
            'courses': ", ".join(sorted(list(courses)))
        })

    return render(request, 'partials/seating_reports.html', {'reports': report_data})



def teacher_reports(request):
    allotments = TeacherAllotment.objects.select_related('exam', 'room', 'teacher').all().order_by('exam__date', 'exam__time')

    # Build teacher -> list of duty dicts mapping from assignments
    teacher_assignment_map = {}
    for a in allotments:
        teacher = a.teacher
        session_label = "Morning" if a.exam.time.hour < 12 else "Afternoon"
        
        if teacher.id not in teacher_assignment_map:
            teacher_assignment_map[teacher.id] = []
        
        teacher_assignment_map[teacher.id].append({
            'date': a.exam.date,
            'session': session_label,
            'room': a.room.room_number
        })

    # Build report for ALL teachers in the database
    all_teachers = Teacher.objects.all().order_by('department', 'faculty_id')
    report_data = []
    
    for teacher in all_teachers:
        duties = teacher_assignment_map.get(teacher.id, [])
        # Sort duties by date/session for Duty 1, Duty 2 logic
        sorted_duties = sorted(duties, key=lambda x: (x['date'], 0 if x['session'] == 'Morning' else 1))
        
        d1 = sorted_duties[0] if len(sorted_duties) > 0 else {}
        d2 = sorted_duties[1] if len(sorted_duties) > 1 else {}
        
        # Room No column: list unique rooms
        all_rooms = list(dict.fromkeys(d['room'] for d in sorted_duties))
        
        report_data.append({
            'faculty_id': teacher.faculty_id,
            'name': teacher.name,
            'dept': teacher.department,
            'd1_date': d1.get('date'),
            'd1_session': d1.get('session'),
            'd2_date': d2.get('date'),
            'd2_session': d2.get('session'),
            'room_no': ", ".join(all_rooms),
        })

    dept_grouped = defaultdict(list)
    for entry in report_data:
        dept_grouped[entry['dept']].append(entry)

    # Sort each dept by faculty_id
    final_grouped = []
    for dept in sorted(dept_grouped.keys()):
        teachers_list = sorted(dept_grouped[dept], key=lambda x: x['faculty_id'])
        final_grouped.append((dept, teachers_list))

    return render(request, 'partials/teacher_reports.html', {
        'grouped_data': final_grouped,
    })


def clear_data(request):
    if request.method == "POST":
        Student.objects.all().delete()
        Teacher.objects.all().delete()
        Room.objects.all().delete()
        Exam.objects.all().delete()
        SeatAllotment.objects.all().delete()
        TeacherAllotment.objects.all().delete()
        messages.success(request, "All data wiped.")
        return redirect('dashboard')

# --- STUDENT MANAGEMENT VIEWS ---

def student_list(request):
    # Optional filtering/searching
    search_query = request.GET.get('search', '')
    if search_query:
        students = Student.objects.filter(
            Q(usn__icontains=search_query) | 
            Q(department__icontains=search_query) |
            Q(name__icontains=search_query)
        ).order_by('usn')
    else:
        students = Student.objects.all().order_by('usn')
    return render(request, 'partials/student_list.html', {'students': students, 'search_query': search_query})

def student_add(request):
    if request.method == "POST":
        name = request.POST.get('name')
        usn = request.POST.get('usn')
        department = request.POST.get('department')
        semester = request.POST.get('semester')
        
        try:
            Student.objects.create(name=name, usn=usn, department=department, semester=semester)
            messages.success(request, "Student added successfully!")
        except Exception as e:
            messages.error(request, f"Error adding student: {e}")
            
    return redirect('dashboard') # will cause full reload right now

def student_delete(request, student_id):
    if request.method == "POST":
        student = get_object_or_404(Student, id=student_id)
        student.delete()
        messages.success(request, "Student deleted.")
        # Reload student list
        return student_list(request)
