from fastapi import APIRouter, Depends, Path, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette import status
from starlette.responses import RedirectResponse
from Routers.auth import get_current_user
import models
from models import Base, ToDo
from database import  engine, SessionLocal
from typing import Annotated
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
import google.generativeai as genai
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage
import markdown
from bs4 import BeautifulSoup

#herbir url nin başında todo ekler
router = APIRouter(
    prefix="/todo",
    tags=["Todo"],
)
#render etmesini sağlar
templates = Jinja2Templates(directory="templates")
#clienttan gelen veri doğru olmalı validation yapıyoruz.
class ToDoRequest(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    priority: int = Field(ge=1, le=10)
    completed: bool

def get_db(): #bütün end pointler bu fonksyiona depend edecek.
    db = SessionLocal()
    try:
        yield db # istek geldiğinde bir database oturumu açar. memory leak i önler.istek bitince kapatır.
        # return gibidir, generator functiondır birden fazla değer döndürür iterate eder.
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]
#bizim  kullanıcılarımız tarafından geliyor mu dependecny olarak kullanmak gerek?
user_dependency = Annotated[dict, Depends(get_current_user)]

def redirect_to_login():#token süresi dolmuşsa veya giriş yapmamışsa.
    redirect_response = RedirectResponse(url="/auth/login-page",status_code=status.HTTP_302_FOUND)
    redirect_response.delete_cookie("access_token")
    return redirect_response
@router.get("/todo-page") # Çerezlerden (cookies/request) token'ı alıp kullanıcıyı doğrular. Veritabanından o kullanıcıya ait
# Todo'ları çeker ve bunları HTML içine gömer.
async def render_todo_page(request: Request, db: db_dependency):
    try:
        user = await get_current_user(request.cookies.get('access_token'))
        if user is None:
            return redirect_to_login()
        todos = db.query(ToDo).filter(ToDo.owner_id == user.get('id')).all()
        return templates.TemplateResponse("todo.html", {"request": request, "todos": todos, "user": user})
    except:
        return redirect_to_login()

@router.get("/add-todo-page")
async def render_add_todo_page(request: Request):
    try:
        user = await get_current_user(request.cookies.get('access_token'))
        if user is None:
            return redirect_to_login()
        return templates.TemplateResponse("add-todo.html", {"request": request, "user": user})
    except:
        return redirect_to_login()


@router.get("/edit-todo-page/{todo_id}")
async def render_edit_todo_page(request: Request, todo_id: int, db: db_dependency):
    try:
        user = await get_current_user(request.cookies.get('access_token'))
        if user is None:
            return redirect_to_login()
        todo = db.query(ToDo).filter(ToDo.id == todo_id).first()
        return templates.TemplateResponse("edit-todo.html", {"request": request, "todo": todo, "user": user})
    except:
        return redirect_to_login()

@router.get("/")
def read_all (user: user_dependency, db:db_dependency):
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return db.query(ToDo).filter(ToDo.owner_id == user.get('id')).all()

@router.get("/todo/{todo_id}", status_code=status.HTTP_200_OK)
async def read_by_id(user: user_dependency, db:db_dependency, todo_id: int = Path(gt=0)):
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    todo = db.query(ToDo).filter(ToDo.id==todo_id).filter(ToDo.owner_id == user.get('id')).first()
    if todo is not None:
        return todo
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

@router.post("/todo", status_code=status.HTTP_201_CREATED)
async def create_todo(user : user_dependency,db:db_dependency, todo_request: ToDoRequest):
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    todo = ToDo(
        title=todo_request.title,
        description=todo_request.description,
        completed=todo_request.completed,
        priority=todo_request.priority,
        owner_id= user.get('id') # sahip olanılan id ye göre create yapılabilecek.
    )
    todo.description= create_todo_with_gemini(todo.description)
    db.add(todo)
    db.commit()

@router.put("/todo/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_todo(user: user_dependency, db:db_dependency, todo_request: ToDoRequest, todo_id: int = Path(gt=0)):
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    todo = db.query(ToDo).filter(ToDo.id==todo_id).filter(ToDo.owner_id == user.get('id')).first()
    if todo is  None:
     raise HTTPException (status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found")
    todo.title = todo_request.title
    todo.description = todo_request.description
    todo.completed = todo_request.completed
    todo.priority = todo_request.priority

    db.add(todo)
    db.commit()
@router.delete("/todo/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_todo(user : user_dependency, db:db_dependency, todo_id: int = Path(gt=0)):
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    todo = db.query(ToDo).filter(ToDo.id==todo_id).filter(ToDo.owner_id== user.get('id')).first()

    if todo is None:
        raise HTTPException (status_code=status.HTTP_404_NOT_FOUND,detail="Todo not found")
    db.delete(todo)
    db.commit()

def markdown_to_text(markdown_string):
    html = markdown.markdown(markdown_string)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()
    return text


def create_todo_with_gemini(todo_string: str):
    load_dotenv()
    genai.configure(api_key=os.environ.get('GOOGLE_API_KEY'))

    llm = ChatGoogleGenerativeAI(model ="gemini-2.5-flash")
    response = llm.invoke(
        [
            HumanMessage(content="I will provide you a todo item to add my to do list. What i want you to do is to create a longer and more comprehensive description of that todo item, my next message will be my todo:"),
            HumanMessage(content=todo_string),
        ]
    )
    return markdown_to_text(response.content)

