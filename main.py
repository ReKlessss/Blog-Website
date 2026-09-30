from os import getenv
from html import unescape
from functools import wraps
from datetime import datetime

from flask import Flask, abort, render_template, redirect, url_for, flash, request
from flask_login import login_user, current_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from flask_ckeditor.utils import cleanify
from resend.exceptions import ResendError
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from dotenv import load_dotenv
import resend

from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm, ContactForm
from models import BlogPost, User, Comment
from database import db, login_manager


# initialization
load_dotenv()
resend.api_key = getenv("RESEND_API_KEY")
app = Flask(__name__)
app.config['SECRET_KEY'] = getenv("SECRET_KEY", default="very-secret-key")
app.config['SQLALCHEMY_DATABASE_URI'] = getenv("DB_URI")

ckeditor = CKEditor(app)
Bootstrap5(app)
login_manager.init_app(app)
db.init_app(app)


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


@app.context_processor
def inject_year():
	return {"current_year": datetime.now().year}


@app.route('/logout')
@login_required
def logout():
	logout_user()
	return redirect(url_for('get_all_posts'))


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
			password=generate_password_hash(form.password.data)
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
			author=current_user
		)
		db.session.add(new_post)
		db.session.commit()
		return redirect(url_for("get_all_posts"))

	return render_template("make-post.html", form=form)


@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
	post = db.get_or_404(BlogPost, post_id)
	edit_form = CreatePostForm(obj=post)
	if edit_form.validate_on_submit():
		edit_form.populate_obj(post)
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
		if possible_user and (not current_user.is_authenticated or current_user.id != possible_user.id):
			flash(f"User with email {form.email.data} already exists. Please login instead!")
			return redirect(url_for("login") if current_user.is_authenticated else url_for("register"))

		clean_body = cleanify(unescape(form.body.data))
		params: resend.Emails.SendParams = {
			"from": "Blog <onboarding@resend.dev>",
			"to": [getenv("RECEIVER")],
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
	with app.app_context():
		db.create_all()

	app.run(debug=False)
