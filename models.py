from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy import String, Text, ForeignKey, func
from flask_login import UserMixin
from datetime import datetime
from database import db
from hashlib import md5


class User(db.Model, UserMixin):
	__tablename__ = "users"
	id: Mapped[int] = mapped_column(primary_key=True)
	username: Mapped[str] = mapped_column(unique=True)
	email: Mapped[str] = mapped_column(unique=True)
	password: Mapped[str] = mapped_column(String(250))
	join_date: Mapped[datetime] = mapped_column(server_default=func.now())
	posts: Mapped[list["BlogPost"]] = relationship(back_populates="author")
	comments: Mapped[list["Comment"]] = relationship(back_populates="author")

	def avatar(self):
		digest = md5(self.email.lower().encode("utf-8")).hexdigest()
		return f"https://www.gravatar.com/avatar/{digest}?d=identicon"


class BlogPost(db.Model):
	__tablename__ = "blog_posts"
	id: Mapped[int] = mapped_column(primary_key=True)
	author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
	title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
	subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
	date: Mapped[datetime] = mapped_column(server_default=func.now())
	body: Mapped[str] = mapped_column(String(1000), nullable=False)
	img_url: Mapped[str] = mapped_column(Text, nullable=False)
	author: Mapped["User"] = relationship(back_populates="posts")
	comments: Mapped[list["Comment"]] = relationship(back_populates="blog")


class Comment(db.Model):
	__tablename__ = "comments"
	id: Mapped[int] = mapped_column(primary_key=True)
	author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
	blog_id: Mapped[int] = mapped_column(ForeignKey("blog_posts.id"))
	date: Mapped[datetime] = mapped_column(server_default=func.now())
	text: Mapped[str] = mapped_column(String(400))
	author: Mapped["User"] = relationship(back_populates="comments")
	blog: Mapped["BlogPost"] = relationship(back_populates="comments")
