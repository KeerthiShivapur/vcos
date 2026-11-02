const fs = require('fs');
let code = fs.readFileSync('app/(app)/docs/embedded-analytics/page.tsx', 'utf8');

// The file ends with:
//   );
// }
// export default EmbeddedAnalyticsDocsPage;

// We need to change it to:
//   );
// };
// 
// return __jsx;
// }
// export default EmbeddedAnalyticsDocsPage;

const oldEnding = `  );\n}\n\nexport default EmbeddedAnalyticsDocsPage;`;

const newEnding = `  );\n};\n\nreturn __jsx;\n}\nexport default EmbeddedAnalyticsDocsPage;`;

if (code.endsWith(oldEnding)) {
  code = code.slice(0, -oldEnding.length) + newEnding;
  fs.writeFileSync('app/(app)/docs/embedded-analytics/page.tsx', code);
  console.log('Fixed!');
} else {
  console.log('Exact ending not found');
  // Try with different whitespace
  const altOldEnding = '  );\n}\n\nexport default EmbeddedAnalyticsDocsPage;';
  if (code.endsWith(altOldEnding)) {
    code = code.slice(0, -altOldEnding.length) + newEnding;
    fs.writeFileSync('app/(app)/docs/embedded-analytics/page.tsx', code);
    console.log('Fixed with alternative!');
  } else {
    console.log('Still not found');
  }
}