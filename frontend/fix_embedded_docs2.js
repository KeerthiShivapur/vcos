const fs = require('fs');
let code = fs.readFileSync('app/(app)/docs/embedded-analytics/page.tsx', 'utf8');

// Fix the ending - replace the closing with return __jsx
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
  console.log('Old ending not found - trying alternative');
  
  // Try the exact match from the lines
  const altOldEnding = `  );
}
}
export default EmbeddedAnalyticsDocsPage;`;

  const altNewEnding = `  );
};

return __jsx;
}
export default EmbeddedAnalyticsDocsPage;`;

  if (code.includes(altOldEnding)) {
    code = code.replace(altOldEnding, altNewEnding);
    fs.writeFileSync('app/(app)/docs/embedded-analytics/page.tsx', code);
    console.log('Fixed with alternative');
  } else {
    console.log('Alternative also not found');
  }
}