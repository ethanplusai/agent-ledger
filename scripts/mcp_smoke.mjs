// Optional integration test against the official MCP TypeScript SDK (not a runtime dependency).
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import assert from 'node:assert/strict';
const sdk=process.env.MCP_SDK_ROOT;
if(!sdk)throw new Error('Set MCP_SDK_ROOT to an installed @modelcontextprotocol/sdk directory.');
const {Client}=await import(pathToFileURL(path.join(sdk,'dist/esm/client/index.js')));
const {StdioClientTransport}=await import(pathToFileURL(path.join(sdk,'dist/esm/client/stdio.js')));
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const temp=await mkdtemp(path.join(tmpdir(),'ledger-mcp-test-'));
const python=process.env.PYTHON||'python3';
const database=path.join(temp,'test.sqlite3');
const fixture=`from pathlib import Path
import sys
from lens.demo_memory import write_memory_demo
from lens.claude import ClaudeImporter
from lens.storage import connect
root=Path(sys.argv[1]);write_memory_demo(root/'claude');db=connect(root/'test.sqlite3');ClaudeImporter(db,root/'claude').run();db.close()
`;
const built=spawnSync(python,['-c',fixture,temp],{cwd:root,encoding:'utf8'});
if(built.status!==0)throw new Error(built.stderr);
const client=new Client({name:'ledger-test',version:'1.0.0'},{capabilities:{}});
try{
 await client.connect(new StdioClientTransport({command:python,args:[path.join(root,'ledger.py'),'--mcp','--database',database],stderr:'pipe'}));
 const {tools}=await client.listTools();assert.equal(tools.length,6);assert.ok(tools.every(t=>t.annotations.readOnlyHint));
 const result=await client.callTool({name:'search_history',arguments:{q:'SQLite'}});
 const data=JSON.parse(result.content[0].text);assert.ok(data.items.length);
 const brief=await client.callTool({name:'project_briefing',arguments:{project:data.items[0].project}});assert.ok(JSON.parse(brief.content[0].text).draft.includes('historical'));
 const read=await client.callTool({name:'read_context',arguments:{citation:data.items[0].citation}});assert.ok(JSON.parse(read.content[0].text).selected.text.includes('SQLite'));
 const bad=await client.callTool({name:'search_history',arguments:{q:7}});assert.equal(bad.isError,true);
 console.log('Official MCP SDK passed: initialization, tool discovery, search/read citations, invalid arguments, clean subprocess shutdown.');
}finally{await client.close();await rm(temp,{recursive:true,force:true});}
