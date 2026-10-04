import {existsSync,symlinkSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
mkdirSync('.next/standalone/.next',{recursive:true});
if(!existsSync('.next/standalone/.next/static'))symlinkSync(resolve('.next/static'),'.next/standalone/.next/static','dir');
if(existsSync('public')&&!existsSync('.next/standalone/public'))symlinkSync(resolve('public'),'.next/standalone/public','dir');
process.env.HOSTNAME='0.0.0.0';
await import('../.next/standalone/server.js');
