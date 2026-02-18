const { Document, Packer, Paragraph, TextRun, Table, TableCell, TableRow, WidthType, BorderStyle, convertInchesToTwip, VerticalAlign, UnderlineType } = require("docx");
const fs = require("fs");

const doc = new Document({
  sections: [{
    properties: {},
    children: [
      // Title
      new Paragraph({
        text: "Allelio User Guide",
        heading: "Heading1",
        thematicBreak: false,
        alignment: "center",
        spacing: { after: 100 },
        run: new TextRun({
          bold: true,
          size: 32,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "Privacy-First Local Genomics Analysis",
        alignment: "center",
        spacing: { after: 400 },
        run: new TextRun({
          italics: true,
          size: 22,
          font: "Arial",
        }),
      }),

      // Introduction
      new Paragraph({
        text: "Introduction",
        heading: "Heading2",
        spacing: { before: 200, after: 100 },
        run: new TextRun({
          bold: true,
          size: 24,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "Allelio is an open-source, privacy-first, local genomics analysis tool that lets you analyze your raw DNA data from services like 23andMe and AncestryDNA. All analysis happens on your computer using ClinVar, GWAS Catalog, and a local AI (Ollama) – your data never leaves your system.",
        spacing: { after: 100 },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "MIT Licensed. Non-commercial, a gift to humanity.",
        spacing: { after: 200 },
        run: new TextRun({
          italics: true,
          size: 22,
          font: "Arial",
        }),
      }),

      // Prerequisites
      new Paragraph({
        text: "Prerequisites",
        heading: "Heading2",
        spacing: { before: 200, after: 100 },
        run: new TextRun({
          bold: true,
          size: 24,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "Before installing Allelio, ensure you have:",
        spacing: { after: 50 },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "Python 3.9 or later",
        spacing: { before: 50, after: 50 },
        numbering: {
          level: 0,
          reference: "bullet1",
        },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "Ollama installed and running on your system",
        spacing: { after: 50 },
        numbering: {
          level: 0,
          reference: "bullet1",
        },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "4–8 GB of available RAM",
        spacing: { after: 200 },
        numbering: {
          level: 0,
          reference: "bullet1",
        },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),

      // Step 1: Installation
      new Paragraph({
        text: "Step 1: Installation",
        heading: "Heading2",
        spacing: { before: 200, after: 100 },
        run: new TextRun({
          bold: true,
          size: 24,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "Install Allelio using pip:",
        spacing: { after: 50 },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "pip install allelio",
        spacing: { after: 200 },
        border: {
          top: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
          bottom: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
          left: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
          right: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
        },
        shading: { fill: "F5F5F5" },
        run: new TextRun({
          font: "Courier New",
          size: 20,
        }),
      }),

      // Step 2: Setup
      new Paragraph({
        text: "Step 2: Setup",
        heading: "Heading2",
        spacing: { before: 200, after: 100 },
        run: new TextRun({
          bold: true,
          size: 24,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "Run the setup command to download ClinVar and GWAS databases:",
        spacing: { after: 50 },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "allelio setup",
        spacing: { after: 100 },
        border: {
          top: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
          bottom: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
          left: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
          right: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
        },
        shading: { fill: "F5F5F5" },
        run: new TextRun({
          font: "Courier New",
          size: 20,
        }),
      }),
      new Paragraph({
        text: "This process may take several minutes depending on your internet connection. The databases will be stored locally on your computer.",
        spacing: { after: 200 },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),

      // Step 3: Getting Your Raw Data
      new Paragraph({
        text: "Step 3: Getting Your Raw Data File",
        heading: "Heading2",
        spacing: { before: 200, after: 100 },
        run: new TextRun({
          bold: true,
          size: 24,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "From 23andMe:",
        spacing: { after: 50 },
        numbering: {
          level: 0,
          reference: "bullet1",
        },
        run: new TextRun({
          size: 22,
          font: "Arial",
          bold: true,
        }),
      }),
      new Paragraph({
        text: "Go to Your Genetics → Browse Raw Data → Download",
        spacing: { after: 100 },
        numbering: {
          level: 1,
          reference: "bullet1",
        },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "From AncestryDNA:",
        spacing: { after: 50 },
        numbering: {
          level: 0,
          reference: "bullet1",
        },
        run: new TextRun({
          size: 22,
          font: "Arial",
          bold: true,
        }),
      }),
      new Paragraph({
        text: "Go to Account Settings → DNA Settings → Download Your Raw DNA Data",
        spacing: { after: 200 },
        numbering: {
          level: 1,
          reference: "bullet1",
        },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),

      // Step 4: Running Analysis
      new Paragraph({
        text: "Step 4: Running Analysis",
        heading: "Heading2",
        spacing: { before: 200, after: 100 },
        run: new TextRun({
          bold: true,
          size: 24,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "Run the analysis command with your raw data file:",
        spacing: { after: 50 },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "allelio analyze myfile.txt",
        spacing: { after: 100 },
        border: {
          top: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
          bottom: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
          left: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
          right: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
        },
        shading: { fill: "F5F5F5" },
        run: new TextRun({
          font: "Courier New",
          size: 20,
        }),
      }),
      new Paragraph({
        text: "Replace myfile.txt with the path to your downloaded raw data file. The analysis may take 5–15 minutes depending on your system and the AI model in use.",
        spacing: { after: 200 },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),

      // Step 5: Using the Web UI
      new Paragraph({
        text: "Step 5: Using the Web UI",
        heading: "Heading2",
        spacing: { before: 200, after: 100 },
        run: new TextRun({
          bold: true,
          size: 24,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "Start the web server:",
        spacing: { after: 50 },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "allelio serve",
        spacing: { after: 100 },
        border: {
          top: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
          bottom: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
          left: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
          right: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
        },
        shading: { fill: "F5F5F5" },
        run: new TextRun({
          font: "Courier New",
          size: 20,
        }),
      }),
      new Paragraph({
        text: "Open your web browser and navigate to http://localhost:8000 to view your analysis results in an interactive interface.",
        spacing: { after: 200 },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),

      // Step 6: Understanding Your Results
      new Paragraph({
        text: "Step 6: Understanding Your Results",
        heading: "Heading2",
        spacing: { before: 200, after: 100 },
        run: new TextRun({
          bold: true,
          size: 24,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "Your results are organized into the following categories:",
        spacing: { after: 100 },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "Health Conditions – Variants associated with diseases and health risks",
        spacing: { after: 50 },
        numbering: {
          level: 0,
          reference: "bullet1",
        },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "Risk Factors – Genetic predispositions to conditions",
        spacing: { after: 50 },
        numbering: {
          level: 0,
          reference: "bullet1",
        },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "Pharmacogenomics – How your genes affect medication response",
        spacing: { after: 50 },
        numbering: {
          level: 0,
          reference: "bullet1",
        },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "Traits – Non-medical genetic traits (e.g., eye color, caffeine metabolism)",
        spacing: { after: 50 },
        numbering: {
          level: 0,
          reference: "bullet1",
        },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "Carrier Status – Genes you carry that may affect future generations",
        spacing: { after: 200 },
        numbering: {
          level: 0,
          reference: "bullet1",
        },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),

      // Clinical Significance Levels
      new Paragraph({
        text: "Clinical Significance Levels",
        heading: "Heading3",
        spacing: { before: 100, after: 100 },
        run: new TextRun({
          bold: true,
          size: 22,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "Each variant is assigned a clinical significance level:",
        spacing: { after: 100 },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),
      new Table({
        width: { size: 100, type: WidthType.PERCENTAGE },
        rows: [
          new TableRow({
            children: [
              new TableCell({
                children: [new Paragraph({ text: "Level", bold: true, run: new TextRun({ bold: true, font: "Arial" }) })],
                shading: { fill: "D3D3D3" },
                verticalAlign: VerticalAlign.CENTER,
              }),
              new TableCell({
                children: [new Paragraph({ text: "Description", bold: true, run: new TextRun({ bold: true, font: "Arial" }) })],
                shading: { fill: "D3D3D3" },
                verticalAlign: VerticalAlign.CENTER,
              }),
            ],
          }),
          new TableRow({
            children: [
              new TableCell({
                children: [new Paragraph({ text: "Pathogenic", run: new TextRun({ font: "Arial" }) })],
                verticalAlign: VerticalAlign.CENTER,
              }),
              new TableCell({
                children: [new Paragraph({ text: "Strongly associated with disease", run: new TextRun({ font: "Arial" }) })],
                verticalAlign: VerticalAlign.CENTER,
              }),
            ],
          }),
          new TableRow({
            children: [
              new TableCell({
                children: [new Paragraph({ text: "Likely Pathogenic", run: new TextRun({ font: "Arial" }) })],
                verticalAlign: VerticalAlign.CENTER,
              }),
              new TableCell({
                children: [new Paragraph({ text: "Likely associated with disease", run: new TextRun({ font: "Arial" }) })],
                verticalAlign: VerticalAlign.CENTER,
              }),
            ],
          }),
          new TableRow({
            children: [
              new TableCell({
                children: [new Paragraph({ text: "Uncertain Significance", run: new TextRun({ font: "Arial" }) })],
                verticalAlign: VerticalAlign.CENTER,
              }),
              new TableCell({
                children: [new Paragraph({ text: "Unknown clinical significance", run: new TextRun({ font: "Arial" }) })],
                verticalAlign: VerticalAlign.CENTER,
              }),
            ],
          }),
          new TableRow({
            children: [
              new TableCell({
                children: [new Paragraph({ text: "Likely Benign", run: new TextRun({ font: "Arial" }) })],
                verticalAlign: VerticalAlign.CENTER,
              }),
              new TableCell({
                children: [new Paragraph({ text: "Probably not disease-causing", run: new TextRun({ font: "Arial" }) })],
                verticalAlign: VerticalAlign.CENTER,
              }),
            ],
          }),
          new TableRow({
            children: [
              new TableCell({
                children: [new Paragraph({ text: "Benign", run: new TextRun({ font: "Arial" }) })],
                verticalAlign: VerticalAlign.CENTER,
              }),
              new TableCell({
                children: [new Paragraph({ text: "Not associated with disease", run: new TextRun({ font: "Arial" }) })],
                verticalAlign: VerticalAlign.CENTER,
              }),
            ],
          }),
        ],
      }),
      new Paragraph({ text: "", spacing: { after: 200 } }),

      // Step 7: AI Explanations
      new Paragraph({
        text: "Step 7: AI-Generated Explanations",
        heading: "Heading2",
        spacing: { before: 200, after: 100 },
        run: new TextRun({
          bold: true,
          size: 24,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "Allelio uses a local AI (Ollama) to provide plain-English explanations of your results. These explanations are powered by an LLM running on your computer, and your data is ",
        spacing: { after: 200 },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
        children: [
          new TextRun({
            text: "never sent to the internet",
            bold: true,
            size: 22,
            font: "Arial",
          }),
          new TextRun({
            text: ". AI-generated content should be reviewed critically – it may contain errors or miss important nuances.",
            size: 22,
            font: "Arial",
          }),
        ],
      }),

      // Step 8: Generating Reports
      new Paragraph({
        text: "Step 8: Generating Reports",
        heading: "Heading2",
        spacing: { before: 200, after: 100 },
        run: new TextRun({
          bold: true,
          size: 24,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "Generate a PDF or HTML report of your analysis:",
        spacing: { after: 50 },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "allelio analyze myfile.txt --report",
        spacing: { after: 100 },
        border: {
          top: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
          bottom: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
          left: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
          right: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
        },
        shading: { fill: "F5F5F5" },
        run: new TextRun({
          font: "Courier New",
          size: 20,
        }),
      }),
      new Paragraph({
        text: "A report file will be generated in your current directory with the date and time in the filename.",
        spacing: { after: 200 },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),

      // Step 9: Updating Databases
      new Paragraph({
        text: "Step 9: Updating Databases",
        heading: "Heading2",
        spacing: { before: 200, after: 100 },
        run: new TextRun({
          bold: true,
          size: 24,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "Keep your ClinVar and GWAS databases up to date:",
        spacing: { after: 50 },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "allelio update",
        spacing: { after: 100 },
        border: {
          top: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
          bottom: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
          left: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
          right: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE },
        },
        shading: { fill: "F5F5F5" },
        run: new TextRun({
          font: "Courier New",
          size: 20,
        }),
      }),
      new Paragraph({
        text: "Run this command periodically (monthly recommended) to ensure you have the latest genetic data.",
        spacing: { after: 200 },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),

      // Troubleshooting
      new Paragraph({
        text: "Troubleshooting",
        heading: "Heading2",
        spacing: { before: 200, after: 100 },
        run: new TextRun({
          bold: true,
          size: 24,
          font: "Arial",
        }),
      }),
      new Table({
        width: { size: 100, type: WidthType.PERCENTAGE },
        rows: [
          new TableRow({
            children: [
              new TableCell({
                children: [new Paragraph({ text: "Issue", bold: true, run: new TextRun({ bold: true, font: "Arial" }) })],
                shading: { fill: "D3D3D3" },
                verticalAlign: VerticalAlign.CENTER,
              }),
              new TableCell({
                children: [new Paragraph({ text: "Solution", bold: true, run: new TextRun({ bold: true, font: "Arial" }) })],
                shading: { fill: "D3D3D3" },
                verticalAlign: VerticalAlign.CENTER,
              }),
            ],
          }),
          new TableRow({
            children: [
              new TableCell({
                children: [new Paragraph({ text: "Ollama not found", run: new TextRun({ font: "Arial" }) })],
                verticalAlign: VerticalAlign.CENTER,
              }),
              new TableCell({
                children: [new Paragraph({ text: "Install Ollama from ollama.ai and ensure it's running", run: new TextRun({ font: "Arial" }) })],
                verticalAlign: VerticalAlign.CENTER,
              }),
            ],
          }),
          new TableRow({
            children: [
              new TableCell({
                children: [new Paragraph({ text: "Database download fails", run: new TextRun({ font: "Arial" }) })],
                verticalAlign: VerticalAlign.CENTER,
              }),
              new TableCell({
                children: [new Paragraph({ text: "Check internet connection; try 'allelio setup' again", run: new TextRun({ font: "Arial" }) })],
                verticalAlign: VerticalAlign.CENTER,
              }),
            ],
          }),
          new TableRow({
            children: [
              new TableCell({
                children: [new Paragraph({ text: "No variants found", run: new TextRun({ font: "Arial" }) })],
                verticalAlign: VerticalAlign.CENTER,
              }),
              new TableCell({
                children: [new Paragraph({ text: "Verify you have the correct raw data file format; check file contents", run: new TextRun({ font: "Arial" }) })],
                verticalAlign: VerticalAlign.CENTER,
              }),
            ],
          }),
          new TableRow({
            children: [
              new TableCell({
                children: [new Paragraph({ text: "Slow analysis", run: new TextRun({ font: "Arial" }) })],
                verticalAlign: VerticalAlign.CENTER,
              }),
              new TableCell({
                children: [new Paragraph({ text: "Close other applications; increase available RAM or CPU", run: new TextRun({ font: "Arial" }) })],
                verticalAlign: VerticalAlign.CENTER,
              }),
            ],
          }),
        ],
      }),
      new Paragraph({ text: "", spacing: { after: 200 } }),

      // Privacy & Disclaimer
      new Paragraph({
        text: "Privacy & Disclaimer",
        heading: "Heading2",
        spacing: { before: 200, after: 100 },
        run: new TextRun({
          bold: true,
          size: 24,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "All data stays local. Your raw DNA file and analysis results remain on your computer. Allelio does not send your genetic data to any server or cloud service.",
        spacing: { after: 100 },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "Allelio is educational software only and is not a medical device. It is not intended for clinical diagnosis or medical decision-making. Always consult with a healthcare provider before making any health decisions based on genetic information.",
        spacing: { after: 200 },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),

      // Support & More
      new Paragraph({
        text: "Support & Resources",
        heading: "Heading2",
        spacing: { before: 200, after: 100 },
        run: new TextRun({
          bold: true,
          size: 24,
          font: "Arial",
        }),
      }),
      new Paragraph({
        text: "For more information, visit the Allelio GitHub repository or consult the Allelio Disclaimers document for comprehensive legal and medical disclaimers.",
        spacing: { after: 400 },
        run: new TextRun({
          size: 22,
          font: "Arial",
        }),
      }),

      // Footer
      new Paragraph({
        text: "Allelio – A gift to humanity",
        alignment: "center",
        spacing: { before: 200 },
        run: new TextRun({
          italics: true,
          size: 20,
          font: "Arial",
          color: "666666",
        }),
      }),
    ],
  }],
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("/sessions/dreamy-busy-albattani/mnt/Claude/allelio/docs/Allelio_User_Guide.docx", buffer);
  console.log("Allelio_User_Guide.docx created successfully");
});
