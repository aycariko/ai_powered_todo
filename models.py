from database import Base, engine
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey

class ToDo (Base): #databasede oluşturduğumuz basei alıyoruz
    __tablename__ = "todos"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(String)
    priority = Column(Integer)
    completed = Column(Boolean, default=False)
    owner_id = Column(Integer, ForeignKey('users.id')) #bunu sonradan ekledik ve dbye eklenmedi
    # migration yolu ile yapılmalı


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    role =Column(String)
    phone_number = Column(String)



