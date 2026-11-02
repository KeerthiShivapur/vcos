const fs = require('fs');
let code = fs.readFileSync('app/(app)/docs/embedded-analytics/page.tsx', 'utf8');

// Find the position of the last `  );\n}` pattern
const endPattern = /  \);\n}\n}\n\nexport default EmbeddedAnalyticsDocsPage;/;
const match = code.match(endPattern);
if (match) {
  console.log('Found pattern at index:', match.index);
  const fixed = code.substring(0, match.index) + '  );\n};\n\nreturn __jsx;\n}\n\nexport default EmbeddedAnalyticsDocsPage;';
  fs.writeFileSync('app/(app)/docs/embedded-analytics/page.tsx', fixed);
  console.log('Fixed!');
} else {
  console.log('Pattern not found, trying different approach');
  // Find the last occurrence of "  );"
  const lastReturn = code.lastIndexOf('  );');
  console.log('Last "  );" at:', lastReturn);
  console.log('Context:', code.substring(lastReturn - 50, lastReturn + 50));
}