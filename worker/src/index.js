/**
 * Cloudflare Worker for one-click Zotero paper import
 *
 * Uses HMAC-signed URLs to prevent unauthorized requests.
 *
 * Endpoints:
 *   GET /add?data=<base64>&ts=<timestamp>&sig=<signature> - Add paper to Zotero
 *   GET /health - Health check
 *
 * Required secrets (set via `wrangler secret put`):
 *   ZOTERO_API_KEY - Your Zotero API key
 *   ZOTERO_USER_ID - Your Zotero user ID
 *   SIGNING_SECRET - Secret for HMAC signatures (generate with: openssl rand -hex 32)
 */

const ZOTERO_API_BASE = 'https://api.zotero.org';
const URL_EXPIRY_HOURS = 168; // Links valid for 7 days

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    // CORS headers for browser requests
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    };

    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    try {
      if (path === '/health') {
        return jsonResponse({ status: 'ok', timestamp: Date.now() }, corsHeaders);
      }

      if (path === '/add') {
        return await handleAddPaper(url, env, corsHeaders);
      }

      // Default: show usage info
      return htmlResponse(renderHomePage(), corsHeaders);

    } catch (error) {
      console.error('Worker error:', error);
      return htmlResponse(renderErrorPage(error.message), corsHeaders, 500);
    }
  },
};

/**
 * Handle adding a paper to Zotero
 */
async function handleAddPaper(url, env, corsHeaders) {
  // Check for required secrets
  if (!env.ZOTERO_API_KEY || !env.ZOTERO_USER_ID) {
    throw new Error('Zotero credentials not configured');
  }
  if (!env.SIGNING_SECRET) {
    throw new Error('Signing secret not configured');
  }

  // Get parameters
  const encodedData = url.searchParams.get('data');
  const timestamp = url.searchParams.get('ts');
  const signature = url.searchParams.get('sig');

  if (!encodedData || !timestamp || !signature) {
    throw new Error('Missing required parameters (data, ts, sig)');
  }

  // Verify timestamp (prevent replay attacks)
  const ts = parseInt(timestamp, 10);
  const now = Date.now();
  const age = now - ts;
  const maxAge = URL_EXPIRY_HOURS * 60 * 60 * 1000;

  if (isNaN(ts) || age < 0 || age > maxAge) {
    throw new Error('Link has expired. Please generate a new digest.');
  }

  // Verify HMAC signature
  const expectedSig = await generateSignature(encodedData, timestamp, env.SIGNING_SECRET);
  if (signature !== expectedSig) {
    throw new Error('Invalid signature. Link may have been tampered with.');
  }

  // Decode paper metadata
  let paper;
  try {
    const decoded = atob(encodedData.replace(/-/g, '+').replace(/_/g, '/'));
    paper = JSON.parse(decoded);
  } catch (e) {
    throw new Error('Invalid paper data encoding');
  }

  // Validate required fields
  if (!paper.title) {
    throw new Error('Paper title is required');
  }

  // Create Zotero item
  const zoteroItem = createZoteroItem(paper);

  // Send to Zotero API
  const response = await fetch(
    `${ZOTERO_API_BASE}/users/${env.ZOTERO_USER_ID}/items`,
    {
      method: 'POST',
      headers: {
        'Zotero-API-Key': env.ZOTERO_API_KEY,
        'Zotero-API-Version': '3',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify([zoteroItem]),
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    console.error('Zotero API error:', response.status, errorText);

    if (response.status === 403) {
      throw new Error('Zotero API key invalid or lacks write permission');
    }
    throw new Error(`Zotero API error: ${response.status}`);
  }

  const result = await response.json();

  // Get the created item key
  const itemKey = result.successful?.['0']?.key;
  const zoteroUrl = itemKey
    ? `https://www.zotero.org/users/${env.ZOTERO_USER_ID}/items/${itemKey}`
    : null;

  return htmlResponse(renderSuccessPage(paper.title, zoteroUrl), corsHeaders);
}

/**
 * Generate HMAC-SHA256 signature
 */
async function generateSignature(data, timestamp, secret) {
  const encoder = new TextEncoder();
  const message = `${data}.${timestamp}`;

  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );

  const signature = await crypto.subtle.sign('HMAC', key, encoder.encode(message));

  // Convert to hex string
  return Array.from(new Uint8Array(signature))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

/**
 * Convert paper metadata to Zotero item format
 */
function createZoteroItem(paper) {
  // Determine item type
  let itemType = 'journalArticle';
  if (paper.journal?.toLowerCase().includes('preprint') ||
      paper.journal?.toLowerCase().includes('rxiv')) {
    itemType = 'preprint';
  }

  // Format authors for Zotero
  const creators = (paper.authors || []).slice(0, 20).map(author => {
    // Handle "Last Initials" format (e.g., "Smith JK")
    const match = author.match(/^([^,]+?)\s+([A-Z]+)$/);
    if (match) {
      return {
        creatorType: 'author',
        lastName: match[1],
        firstName: match[2].split('').join('. ') + '.',
      };
    }

    // Handle "Last, First" format
    if (author.includes(',')) {
      const [lastName, firstName] = author.split(',').map(s => s.trim());
      return { creatorType: 'author', lastName, firstName };
    }

    // Fallback: try to split on last space
    const lastSpace = author.lastIndexOf(' ');
    if (lastSpace > 0) {
      return {
        creatorType: 'author',
        firstName: author.slice(0, lastSpace),
        lastName: author.slice(lastSpace + 1),
      };
    }

    return { creatorType: 'author', name: author };
  });

  // Build the item
  const item = {
    itemType,
    title: paper.title,
    creators,
    abstractNote: paper.abstract || '',
    date: paper.date || '',
    url: paper.url || '',
    DOI: paper.doi || '',
    publicationTitle: paper.journal || '',
    tags: [
      { tag: 'lit-monitor' },
    ],
  };

  return item;
}

// Helper functions
function jsonResponse(data, corsHeaders, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...corsHeaders },
  });
}

function htmlResponse(html, corsHeaders, status = 200) {
  return new Response(html, {
    status,
    headers: { 'Content-Type': 'text/html', ...corsHeaders },
  });
}

function renderHomePage() {
  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Literature Monitor - Zotero Worker</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }
    h1 { color: #2c3e50; }
    code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }
    .status { color: #27ae60; }
  </style>
</head>
<body>
  <h1>Literature Monitor - Zotero Worker</h1>
  <p class="status">✓ Worker is running</p>
  <p>This worker handles one-click paper imports to Zotero from the Literature Monitor digest.</p>
  <p>Links are cryptographically signed and expire after 7 days for security.</p>
</body>
</html>`;
}

function renderSuccessPage(title, zoteroUrl) {
  const viewLink = zoteroUrl
    ? `<p><a href="${zoteroUrl}" target="_blank" style="color: #3498db;">View in Zotero →</a></p>`
    : '';

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Added to Zotero</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; text-align: center; }
    .success { color: #27ae60; font-size: 64px; margin-bottom: 10px; }
    h1 { color: #2c3e50; margin-top: 0; }
    .title { color: #666; font-style: italic; margin: 20px; padding: 15px; background: #f8f8f8; border-radius: 6px; }
  </style>
</head>
<body>
  <div class="success">✓</div>
  <h1>Added to Zotero!</h1>
  <p class="title">${escapeHtml(title)}</p>
  ${viewLink}
  <p><small>You can close this tab.</small></p>
</body>
</html>`;
}

function renderErrorPage(message) {
  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Error - Zotero Worker</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; text-align: center; }
    .error { color: #e74c3c; font-size: 64px; margin-bottom: 10px; }
    h1 { color: #2c3e50; margin-top: 0; }
    .message { color: #c0392b; background: #fdf2f2; padding: 15px; border-radius: 6px; margin: 20px 0; }
  </style>
</head>
<body>
  <div class="error">✗</div>
  <h1>Could not add to Zotero</h1>
  <p class="message">${escapeHtml(message)}</p>
</body>
</html>`;
}

function escapeHtml(text) {
  if (!text) return '';
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
