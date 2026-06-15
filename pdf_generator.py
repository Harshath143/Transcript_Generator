import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Flowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

class PageTracker(Flowable):
    """
    A custom zero-size flowable that records the page number where it is rendered.
    Used to build the dynamic Table of Contents.
    """
    def __init__(self, key, registry):
        super().__init__()
        self.key = key
        self.registry = registry
        
    def draw(self):
        # self.canv is the active canvas during drawing
        self.registry[self.key] = self.canv.getPageNumber()
        
    def wrap(self, availWidth, availHeight):
        return 0, 0

class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and render running headers and footers
    with 'Page X of Y' pagination.
    """
    def __init__(self, *args, book_title="Transcript Book", **kwargs):
        super().__init__(*args, **kwargs)
        self.book_title = book_title
        self._saved_page_states = []

    def showPage(self):
        # Save page state for post-processing
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_decorations(self, total_pages):
        # Suppress headers/footers on the cover page (Page 1)
        if self._pageNumber == 1:
            return
            
        self.saveState()
        
        # 1. Header (only on pages > 2, suppressing on TOC page)
        if self._pageNumber > 2:
            self.setFont("Helvetica-Bold", 8.5)
            self.setFillColor(HexColor("#475569")) # Slate 600
            self.drawString(54, 745, self.book_title.upper())
            
            # Subtitle or generation note on right side of header
            self.setFont("Helvetica", 8)
            self.setFillColor(HexColor("#94a3b8")) # Slate 400
            self.drawRightString(558, 745, "Module Transcript")
            
            # Decorative line
            self.setStrokeColor(HexColor("#cbd5e1")) # Slate 200
            self.setLineWidth(0.5)
            self.line(54, 737, 558, 737)
            
        # 2. Footer (on all pages except cover)
        self.setFont("Helvetica", 8.5)
        self.setFillColor(HexColor("#64748b")) # Slate 500
        self.drawString(54, 42, "Audio Transcript Book")
        
        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(558, 42, page_str)
        
        # Footer dividing line
        self.setStrokeColor(HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(54, 54, 558, 54)
        
        self.restoreState()

def clean_title(filename: str) -> str:
    """
    Cleans up a filename to turn it into a readable module title.
    E.g. '01_session_intro_v2.mp4' -> 'Module 1: Session Intro'
    """
    # Strip extension
    base = os.path.splitext(filename)[0]
    
    # Replace separators with spaces
    base = base.replace("_", " ").replace("-", " ")
    
    # Check if starts with a digit/sequence number
    parts = base.split()
    if parts and parts[0].isdigit():
        num = int(parts[0])
        rest = " ".join(parts[1:])
        # If rest is empty, just name it e.g. 'Module 1'
        if not rest:
            return f"Module {num}"
        return f"Module {num}: {rest.title()}"
        
    return base.title()

def split_into_paragraphs(text: str) -> list[str]:
    """
    Splits long continuous text into readable paragraphs.
    Respects existing paragraph breaks, but formats wall-of-text transcripts.
    """
    if not text or not text.strip():
        return ["(No transcript content recorded)"]
        
    # Standardize newlines
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    
    # Check if there are already multiple paragraph breaks
    raw_paras = [p.strip() for p in normalized.split("\n\n") if p.strip()]
    if len(raw_paras) > 1:
        # Respect existing structure
        return raw_paras
        
    # If the text has single newlines, try splitting on those first
    raw_paras_single = [p.strip() for p in normalized.split("\n") if p.strip()]
    if len(raw_paras_single) > 3:
        return raw_paras_single
        
    # Wall of text fallback: split by sentences and group
    import re
    sentence_endings = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9])')
    sentences = sentence_endings.split(normalized)
    
    grouped_paras = []
    current_para = []
    
    for sentence in sentences:
        s_clean = sentence.strip()
        if not s_clean:
            continue
        current_para.append(s_clean)
        # Group about 4 sentences per paragraph (approx. 100-150 words)
        if len(current_para) >= 4:
            grouped_paras.append(" ".join(current_para))
            current_para = []
            
    if current_para:
        grouped_paras.append(" ".join(current_para))
        
    return grouped_paras if grouped_paras else [text]

def build_pdf_story(book_title, chapters, registry, styles):
    """
    Constructs the document story (list of flowables) for compilation.
    """
    story = []
    
    # ------------------ 1. COVER PAGE ------------------
    story.append(Spacer(1, 140))
    story.append(Paragraph(book_title.upper(), styles['CoverTitle']))
    story.append(Spacer(1, 15))
    
    # Decorative line (using Table for stability)
    line_table = Table([[""]], colWidths=[504], rowHeights=[3])
    line_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), HexColor("#0d9488")), # Teal accent
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(line_table)
    story.append(Spacer(1, 20))
    
    story.append(Paragraph("A Complete Transcript Compilation and Module Guide", styles['CoverSubtitle']))
    story.append(Spacer(1, 250))
    
    # Date Block
    date_str = datetime.now().strftime("%B %d, %Y")
    story.append(Paragraph(f"Generated on {date_str}", styles['CoverMeta']))
    story.append(Paragraph(f"Modules Total: {len(chapters)}", styles['CoverMeta']))
    story.append(PageBreak())
    
    # ------------------ 2. TABLE OF CONTENTS ------------------
    story.append(Spacer(1, 20))
    story.append(Paragraph("TABLE OF CONTENTS", styles['ChapterHeader']))
    story.append(Spacer(1, 15))
    
    # Draw horizontal divider
    divider = Table([[""]], colWidths=[504], rowHeights=[1])
    divider.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), HexColor("#cbd5e1")),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(divider)
    story.append(Spacer(1, 15))
    
    # Build TOC table entries
    toc_data = []
    for video_file, _ in chapters:
        chapter_title = clean_title(video_file)
        page_num = registry.get(chapter_title, "??")
        
        toc_data.append([
            Paragraph(chapter_title, styles['TOCText']),
            Paragraph(str(page_num), styles['TOCPage'])
        ])
        
    toc_table = Table(toc_data, colWidths=[440, 64])
    toc_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('LINEBELOW', (0,0), (-1,-1), 0.5, HexColor("#f1f5f9")), # Slate 100 border
    ]))
    story.append(toc_table)
    story.append(PageBreak())
    
    # ------------------ 3. CHAPTERS (MODULES) ------------------
    for video_file, text in chapters:
        chapter_title = clean_title(video_file)
        
        # Track the page number for this chapter heading in our registry
        story.append(PageTracker(chapter_title, registry))
        
        # Chapter title formatting
        story.append(Spacer(1, 15))
        story.append(Paragraph(chapter_title, styles['ChapterHeader']))
        story.append(Spacer(1, 8))
        
        # Accent line under chapter header
        ch_divider = Table([[""]], colWidths=[504], rowHeights=[1.5])
        ch_divider.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), HexColor("#0f172a")), # Slate 900
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(ch_divider)
        story.append(Spacer(1, 15))
        
        # Format and write body paragraphs
        paragraphs = split_into_paragraphs(text)
        for para in paragraphs:
            story.append(Paragraph(para, styles['BodyText']))
            story.append(Spacer(1, 8))
            
        story.append(PageBreak())
        
    return story

def generate_pdf(book_title: str, chapters: list[tuple[str, str]], output_pdf_path: str):
    """
    Orchestrates the two-pass compilation of the PDF:
    Pass 1: Renders page numbers to the registry.
    Pass 2: Builds the actual document with real page numbers in the TOC.
    """
    print(f"Generating PDF: {os.path.basename(output_pdf_path)}...")
    
    # Page dimensions and base setup
    # Letter is 612x792 pt. Margins: left=54, right=54, top=64, bottom=72
    # Document printable width = 504
    doc = SimpleDocTemplate(
        output_pdf_path,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=64,
        bottomMargin=72
    )
    
    # Styles definition
    base_styles = getSampleStyleSheet()
    styles = {}
    
    styles['CoverTitle'] = ParagraphStyle(
        'CoverTitleStyle',
        parent=base_styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=30,
        leading=36,
        textColor=HexColor('#0f172a'),
        alignment=1 # Center
    )
    
    styles['CoverSubtitle'] = ParagraphStyle(
        'CoverSubtitleStyle',
        parent=base_styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        leading=16,
        textColor=HexColor('#475569'),
        alignment=1 # Center
    )
    
    styles['CoverMeta'] = ParagraphStyle(
        'CoverMetaStyle',
        parent=base_styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=HexColor('#64748b'),
        alignment=1 # Center
    )
    
    styles['ChapterHeader'] = ParagraphStyle(
        'ChapterHeaderStyle',
        parent=base_styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=HexColor('#0f172a'),
        keepWithNext=True
    )
    
    styles['BodyText'] = ParagraphStyle(
        'BodyTextStyle',
        parent=base_styles['Normal'],
        fontName='Helvetica',
        fontSize=10.5,
        leading=15.5,
        textColor=HexColor('#334155'),
        alignment=4 # Justified for book-like clean margins
    )
    
    styles['TOCText'] = ParagraphStyle(
        'TOCTextStyle',
        parent=base_styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=14,
        textColor=HexColor('#1e293b')
    )
    
    styles['TOCPage'] = ParagraphStyle(
        'TOCPageStyle',
        parent=base_styles['Normal'],
        fontName='Helvetica',
        fontSize=10.5,
        leading=14,
        textColor=HexColor('#475569'),
        alignment=2 # Right aligned
    )
    
    # Registry to store {chapter_title: page_number}
    registry = {}
    
    # Define custom canvasmaker to inject book title
    custom_canvasmaker = lambda *args, **kwargs: NumberedCanvas(*args, book_title=book_title, **kwargs)
    
    # ------------------ PASS 1 ------------------
    # Generate temporary PDF to populate page tracker registry
    print(" -> Pass 1: Calculating page allocations...")
    story_pass1 = build_pdf_story(book_title, chapters, registry, styles)
    doc.build(story_pass1, canvasmaker=custom_canvasmaker)
    
    # ------------------ PASS 2 ------------------
    # Re-build PDF using the mapped page numbers for the TOC
    print(" -> Pass 2: Rendering final compiled document...")
    story_pass2 = build_pdf_story(book_title, chapters, registry, styles)
    doc.build(story_pass2, canvasmaker=custom_canvasmaker)
    
    print("PDF generation complete!")
