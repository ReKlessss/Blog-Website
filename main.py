from csv import excel
from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash, request
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_ckeditor.utils import cleanify
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, ForeignKey
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm, ContactForm
from hashlib import md5
from dotenv import load_dotenv
from resend.exceptions import ResendError
import resend
from html import unescape
import os

load_dotenv()
resend.api_key = os.getenv("RESEND_API_KEY")
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", default="very-secret-key")
ckeditor = CKEditor(app)
Bootstrap5(app)

login_manager = LoginManager()
login_manager.init_app(app)


# CREATE DATABASE
class Base(DeclarativeBase):
	pass


app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DB_URI")
db = SQLAlchemy(model_class=Base)
db.init_app(app)


# CONFIGURE TABLES
class BlogPost(db.Model):
	__tablename__ = "blog_posts"
	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
	title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
	subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
	date: Mapped[str] = mapped_column(String(250), nullable=False)
	body: Mapped[str] = mapped_column(Text, nullable=False)
	author: Mapped["User"] = relationship(back_populates="posts")
	img_url: Mapped[str] = mapped_column(String(250), nullable=False)
	comments: Mapped[list["Comment"]] = relationship(back_populates="blog")


class Comment(db.Model):
	__tablename__ = "comments"
	id: Mapped[int] = mapped_column(primary_key=True)
	author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
	author: Mapped["User"] = relationship(back_populates="comments")
	blog_id: Mapped[int] = mapped_column(ForeignKey("blog_posts.id"))
	blog: Mapped["BlogPost"] = relationship(back_populates="comments")
	text: Mapped[str] = mapped_column(String(250))


class User(db.Model, UserMixin):
	__tablename__ = "users"
	id: Mapped[int] = mapped_column(primary_key=True)
	username: Mapped[str] = mapped_column(unique=True)
	email: Mapped[str] = mapped_column(unique=True)
	password: Mapped[str] = mapped_column(String(250))
	posts: Mapped[list["BlogPost"]] = relationship(back_populates="author")
	comments: Mapped[list["Comment"]] = relationship(back_populates="author")

	def avatar(self):
		digest = md5(self.email.lower().encode("utf-8")).hexdigest()
		return f"https://www.gravatar.com/avatar/{digest}?d=identicon"


def admin_only(func):
	@wraps(func)
	def wrapper(*args, **kwargs):
		if current_user.get_id() != "1":
			abort(403)
		else:
			return func(*args, **kwargs)

	return wrapper


@login_manager.user_loader
def load_user(user_id):
	user = db.session.get(User, user_id)
	return user


with app.app_context():
	db.create_all()


@app.route('/register', methods=["GET", "POST"])
def register():
	form = RegisterForm()

	if form.validate_on_submit():
		possible_user = db.session.scalar(db.select(User).where(User.email == form.email.data))
		if possible_user:
			flash(f"User with email {form.email.data} already exists. Please login instead!")
			return redirect(url_for("login"))

		new_user = User(
			username=form.username.data,
			email=form.email.data,
			password=generate_password_hash(form.password.data, method="pbkdf2:sha256", salt_length=12)
		)

		db.session.add(new_user)
		db.session.commit()

		login_user(new_user)
		return redirect(url_for("get_all_posts"))

	return render_template("register.html", form=form)


@app.route('/login', methods=["GET", "POST"])
def login():
	form = LoginForm()

	if form.validate_on_submit():
		user = db.session.scalar(db.select(User).where(User.email == form.email.data))
		if not user:
			flash("Invalid email, please try again.")
			return redirect(url_for("login"))

		if not check_password_hash(user.password, form.password.data):
			flash("Invalid password, please try again.")
			return redirect(url_for("login"))

		login_user(user)
		return redirect(url_for("get_all_posts"))

	return render_template("login.html", form=form)


@app.route('/logout')
@login_required
def logout():
	logout_user()
	return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
	result = db.session.execute(db.select(BlogPost))
	posts = result.scalars().all()
	return render_template("index.html", all_posts=posts)


@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
	requested_post = db.get_or_404(BlogPost, post_id)
	form = CommentForm()

	if form.validate_on_submit():
		if not current_user.is_authenticated:
			flash("You can't comment until you log in!")
			return redirect(url_for("login"))

		comment = Comment(author=current_user, blog=requested_post, text=form.comment.data)

		db.session.add(comment)
		db.session.commit()

		return redirect(url_for("get_all_posts"))

	return render_template("post.html", post=requested_post, form=form)


# TODO: Use a decorator so only an admin user can create a new post
@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
	form = CreatePostForm()
	if form.validate_on_submit():
		clean_text = cleanify(unescape(form.body.data))

		new_post = BlogPost(
			title=form.title.data,
			subtitle=form.subtitle.data,
			body=clean_text,
			img_url=form.img_url.data,
			author=current_user,
			date=date.today().strftime("%B %d, %Y")
		)
		db.session.add(new_post)
		db.session.commit()
		return redirect(url_for("get_all_posts"))

	return render_template("make-post.html", form=form)


@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
	post = db.get_or_404(BlogPost, post_id)
	edit_form = CreatePostForm(
		title=post.title,
		subtitle=post.subtitle,
		img_url=post.img_url,
		author=post.author,
		body=post.body
	)
	if edit_form.validate_on_submit():
		post.title = edit_form.title.data
		post.subtitle = edit_form.subtitle.data
		post.img_url = edit_form.img_url.data
		post.author = current_user
		post.body = edit_form.body.data
		db.session.commit()
		return redirect(url_for("show_post", post_id=post.id))
	return render_template("make-post.html", form=edit_form, is_edit=True)


@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
	post_to_delete = db.get_or_404(BlogPost, post_id)
	db.session.delete(post_to_delete)
	db.session.commit()
	return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
	return render_template("about.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
	form = ContactForm()

	if request.method == "GET" and current_user.is_authenticated:
		form.email.data = current_user.email

	if form.validate_on_submit():
		possible_user = db.session.scalar(db.select(User).where(User.email == form.email.data))
		if current_user.is_authenticated:
			if possible_user.id != current_user.id:
				flash(f"Cannot send messages for a user that already exists unless logged in. Please login first!")
				return redirect(url_for("login"))
		else:
			if possible_user:
				flash(f"Cannot send messages for a user that already exists unless logged in. Please login first!")
				return redirect(url_for("login"))


		clean_body = cleanify(unescape(form.body.data))
		params: resend.Emails.SendParams = {
			"from": "Blog <onboarding@resend.dev>",
			"to": [os.getenv("RECEIVER")],
			"subject": f"Message from {form.name.data} ({form.email.data}) on your Blog website",
			"html": clean_body
		}

		try:
			resend.Emails.send(params=params)
			flash("Message sent successfully!")
		except ResendError as e:
			flash(f"Error sending message: {e}")


		return redirect(url_for('contact'))

	return render_template("contact.html", form=form)


if __name__ == "__main__":
	app.run(debug=True)
