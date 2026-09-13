"""Synthetic socket-observed integration experiments, not a server privacy audit."""
import asyncio
import ipaddress
import json
import socket
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient
from allelio.cli import allelio
from allelio.database.store import AllelioDB
from allelio.web.app import app
from allelio.web import routes
from allelio.ai.engine import AIEngine
from allelio.analysis.lookup import VariantResult


@pytest.fixture
def observed(monkeypatch):
    attempts=[]
    original=socket.socket.connect
    def guarded(sock, address):
        if isinstance(address, tuple):
            attempts.append(address)
            assert ipaddress.ip_address(address[0]).is_loopback, 'Non-loopback connection attempt'
        return original(sock,address)
    monkeypatch.setattr(socket.socket,'connect',guarded)
    original_ex=socket.socket.connect_ex
    def guarded_ex(sock,address):
        if isinstance(address,tuple):
            attempts.append(address)
            assert ipaddress.ip_address(address[0]).is_loopback, 'Non-loopback connection attempt'
        return original_ex(sock,address)
    monkeypatch.setattr(socket.socket,'connect_ex',guarded_ex)
    return attempts


@pytest.fixture
def installed(tmp_path, monkeypatch):
    path=tmp_path/'db.sqlite'; db=AllelioDB(str(path)); db.initialize()
    db.insert_clinvar_batch([dict(rsid='rs1', gene='SYNTHETIC',clinical_significance='Pathogenic')])
    monkeypatch.setattr(routes,'AllelioDB',lambda: db)
    from allelio import cli
    monkeypatch.setattr(cli,'AllelioDB',lambda: db)
    monkeypatch.setattr(routes.tempfile,'tempdir',str(tmp_path))
    yield db
    db.close()


def test_annotation_cli_and_web_need_no_connections(installed, observed, tmp_path, capsys):
    source=tmp_path/'synthetic.txt'; content='rs1\t1\t100\tAG\n'; source.write_text(content)
    result=CliRunner().invoke(allelio,['analyze',str(source),'--no-ai','-o',str(tmp_path/'report.html')])
    assert result.exit_code==0,result.output
    with TestClient(app,base_url='http://127.0.0.1') as client:
        response=client.post('/api/analyze',data={'no_ai':'true'},files={'file':('sample.txt',content)})
    assert response.status_code==200,response.text
    assert observed==[]
    assert not list(tmp_path.glob('allelio_upload_*'))
    assert content not in result.output+capsys.readouterr().out


def test_failed_upload_is_removed_and_raw_exception_is_not_returned(installed, observed, tmp_path, monkeypatch):
    def fail(path): raise ValueError('PRIVATE_RAW_GENOTYPE_SENTINEL')
    monkeypatch.setattr(routes,'parse_genotype_file',fail)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        response=client.post('/api/analyze',data={'no_ai':'true'},files={'file':('sample.txt','rs1\t1\t100\tAG\n')})
    assert response.status_code==500
    assert 'PRIVATE_RAW' not in response.text
    assert not list(tmp_path.glob('allelio_upload_*'))
    assert observed==[]


@contextmanager
def model_server(redirect=False, disconnect=False):
    received=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            received.append((self.path,b''))
            if disconnect:
                self.close_connection=True
                return
            payload={'models':[{'name':'synthetic:latest','model':'synthetic:latest'}],'data':[{'id':'synthetic:latest'}]}
            self.send_response(200); self.send_header('Content-Type','application/json');self.end_headers()
            self.wfile.write(json.dumps(payload).encode())
        def do_POST(self):
            body=self.rfile.read(int(self.headers.get('Content-Length',0)));received.append((self.path,body))
            if redirect:
                self.send_response(307);self.send_header('Location','http://203.0.113.1/never');self.end_headers();return
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
            msg={'role':'assistant','content':'The annotation is uncertain. This is not a diagnosis.'}
            self.wfile.write(json.dumps({'message':msg,'choices':[{'message':msg}]}).encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try: yield server.server_port,received
    finally: server.shutdown();server.server_close();thread.join()


@pytest.mark.parametrize('provider',['ollama','openai'])
@pytest.mark.parametrize('redirect',[False,True])
def test_real_local_adapters_never_follow_remote_redirect(provider,redirect,observed,monkeypatch):
    monkeypatch.delenv('ALLELIO_OPENAI_BASE',raising=False)
    with model_server(redirect) as (port,received):
        if provider=='openai': monkeypatch.setenv('ALLELIO_OPENAI_BASE',f'http://127.0.0.1:{port}/v1')
        engine=AIEngine(model='synthetic:latest',host=f'http://127.0.0.1:{port}')
        async def run():
            assert await engine.check_connection()
            return await engine.explain(VariantResult('rs1',genotype='AG'))
        result=asyncio.run(run())
    assert any(body for _,body in received), (engine.status, engine.last_error, received)
    assert all(ipaddress.ip_address(a[0]).is_loopback for a in observed)
    assert result.model is None if redirect else result.model is not None


def test_dns_changes_after_validation_do_not_redirect_prompts(observed,monkeypatch):
    real=socket.getaddrinfo
    with model_server() as (port,received):
        monkeypatch.setenv('ALLELIO_OPENAI_BASE',f'http://model.invalid:{port}/v1')
        calls=[]
        def resolve(host,*args,**kwargs):
            if host=='model.invalid':
                calls.append(host)
                return real('127.0.0.1' if len(calls)==1 else '203.0.113.1',*args,**kwargs)
            return real(host,*args,**kwargs)
        monkeypatch.setattr(socket,'getaddrinfo',resolve)
        engine=AIEngine(model='synthetic:latest')
        async def run():
            await engine.check_connection(); await engine.explain(VariantResult('rs1',genotype='AG'))
        asyncio.run(run())
    assert calls==['model.invalid']
    assert any(body for _,body in received)


def test_remote_endpoint_rejected_before_upload_is_read(installed,observed,monkeypatch,tmp_path):
    monkeypatch.setenv('ALLELIO_OPENAI_BASE','http://203.0.113.1:9000/v1')
    with TestClient(app,base_url='http://127.0.0.1') as client:
        response=client.post('/api/analyze',files={'file':('sample.txt','rs1\t1\t100\tAG\n')})
    assert response.status_code==400
    assert observed==[] and not list(tmp_path.glob('allelio_upload_*'))


@pytest.mark.parametrize('provider',['ollama','openai'])
def test_connection_failure_stays_local(provider,observed,monkeypatch):
    monkeypatch.delenv('ALLELIO_OPENAI_BASE',raising=False)
    # Accept and close without an HTTP response: deterministic connection loss.
    with model_server(disconnect=True) as (port,received):
        if provider=='openai':monkeypatch.setenv('ALLELIO_OPENAI_BASE',f'http://127.0.0.1:{port}/v1')
        engine=AIEngine(model='synthetic:latest',host=f'http://127.0.0.1:{port}')
        async def run():
            assert not await engine.check_connection()
            return await engine.explain(VariantResult('rs1',genotype='AG'))
        result=asyncio.run(run())
    assert observed and result.model is None
    assert engine.status=='unreachable'
    assert not any(body for _,body in received)


def test_cli_parser_exception_does_not_echo_raw_data(installed,observed,tmp_path,monkeypatch):
    from allelio import cli
    source=tmp_path/'synthetic.txt';source.write_text('rs1\t1\t100\tAG\n')
    def fail(path):raise ValueError('PRIVATE_RAW_GENOTYPE_SENTINEL')
    monkeypatch.setattr(cli,'parse_genotype_file_with_stats',fail)
    result=CliRunner().invoke(allelio,['analyze',str(source),'--no-ai','-o',str(tmp_path/'report.html')])
    assert result.exit_code!=0 and 'PRIVATE_RAW' not in result.output and not observed
