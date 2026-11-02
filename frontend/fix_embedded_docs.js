const fs = require('fs');
let code = fs.readFileSync('app/(app)/docs/embedded-analytics/page.tsx', 'utf8');

// Fix the ending
const oldEnding = `  );
}
}

export default EmbeddedAnalyticsDocsPage;`;

const newEnding = `  );
};

return __jsx;
}

export default EmbeddedAnalyticsDocsPage;`;

if (code.includes(oldEnding)) {
  code = code.replace(oldEnding, newEnding);
  fs.writeFileSync('app/(app)/docs/embedded-analytics/page.tsx', code);
  console.log('Fixed embedded-analytics docs page');
} else {
  console.log('Old ending not found');
  // Let's check what's at the end
  const lines = code.split('\n');
  for(let i = lines.length - 10; i < lines.length; i++) {
    console.log((i+1) + ': ' + JSON.stringify(lines[i]));
  }
}