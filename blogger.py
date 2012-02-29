#!/usr/bin/python
# -*- coding: utf-8 -*-

import pprint
import sys
import re
import json
import os.path
import os, sys
import time
import base64
import glob
from ftplib import FTP
from jinja2 import Environment, FileSystemLoader, Template
from string import maketrans
import sqlite3
from blog_config import blog_config


class Blogger:
    def __init__(self):
        self.config = blog_config
        self.config["page_title"] = self.config["page_title"].decode("utf-8")

        self.db = sqlite3.connect(self.config["engine_dir"] + "blog_data.db")

    def __del__(self):
        self.db.commit()

    def AddPost(self, post_file, post_id = None):
        lines = open(post_file,"r").read().decode("utf-8").split("\n")

        post_title = ""
        post_keywords = ""
        post_tags = None
        mo = re.search("^title\:(.*?)$", lines[0])
        if mo:

            post_title = mo.group(1)
        else:
            print "No post title"
            exit()

        mo = re.search("^keywords\:(.*?)$", lines[1])
        if mo:
            post_keywords = mo.group(1)
        else:
            print "No post keywords"
            exit(0)

        mo = re.search("^tags\:(.*?)$", lines[2])
        if mo:
            post_tags = mo.group(1).split(",")
            if post_tags[-1] == u'':
                post_tags = post_tags[0:-1] 
        else:
            print "No post tags"
            exit(0)

        post_body = "\n".join(lines[3:])
        post_keywords = post_keywords.strip(" ,")
        post_tags = map(lambda x: x.strip(" ,"), post_tags)
        post_title = post_title.strip(" ")
        c = self.db.cursor()
        if not post_id:
            c.execute("""
            INSERT INTO posts (title, body, created, status, keywords, description)
            VALUES(?, ?, date('now'), ?, ?, ?)""", \
            ( post_title, post_body, 1, post_keywords, ""))
            self.add_tags(post_tags, c.lastrowid)
        else:
            c.execute("""
            UPDATE posts SET title = ? , body = ?, created = date('now'), keywords = ?, need_update = 1 WHERE id = ?""",\
            ( post_title, post_body, post_keywords, post_id))


    def add_tags(self, tags, post_id):
        c = self.db.cursor()
        for tag in tags:
            c.execute("SELECT id,name FROM tags WHERE name = ?", (tag, ))
            tag_data = c.fetchone()
            if  tag_data == None:
                c.execute("INSERT INTO tags (name) VALUES(?)", (tag, ))
                tag_id = c.lastrowid

                c.execute("INSERT INTO post_tags (post_id, tag_id) VALUES(?,?)", (post_id, tag_id,))
            else:
                c.execute("INSERT INTO post_tags (post_id, tag_id) VALUES(?,?)", (post_id, tag_data[0],))

    def GetPosts(self):
        for post in self.get_all_posts():
            deleted = "+"
            print "%5.5s : %s : %s : %s" % (post["id"],
                                                      post["status"],
                                                      post["created"],
                                                      post["title"])


    def DeletePost(self, post_id):
        if self.entries[int(post_id)]["deleted"] != 1:
            self.entries[int(post_id)]["deleted"] = 1
        else:
            self.entries[int(post_id)]["deleted"] = 0
        self.StoreEntries()


    def EditPost(self, post_id, outfile = None):
        post = self.get_post_by_id(post_id)
        tags = self.get_post_tags(post_id)

        self.env = Environment(loader=FileSystemLoader(self.config["engine_dir"] + '/templates'))
        self.env.cache.clear()
        tpl = self.env.get_template('post_edit_form')
        post_tpl = tpl.render({
                "title" : post["title"],
                "tags"  : tags,
                "keywords" : post["keywords"],
                "post_text" : post["body"] } )

        if outfile:
            f = open(outfile,"w")
            f.write(post_tpl.encode("utf-8"))
            f.close()
        else:
            print post_tpl



    def UpdatePost(self, post_id, new_file):
        self.AddPost(new_file, post_id)


    def GenerateBlog(self):
        # first create index pages
        self.env = Environment(loader=FileSystemLoader(self.config["engine_dir"] + '/templates'))
        self.env.cache.clear()

        self.env.filters['spoil'] = self.post_spoil
        self.env.filters['body'] = self.post_body
        self.env.filters['b64'] = base64.b64encode
        self.env.filters['month_name'] = self.month_name
        self.env.filters['get_tags_string'] = self.get_tags_string


        self.hrono_and_tags_map()


        self.GenerateIndexPages(self.env.get_template('page.html'))
        self.GeneratePostPages(self.env.get_template('post.html'))
        self.GenerateTagsPages(self.env.get_template('tags.html'))
        self.GenerateHronoPages(self.env.get_template('calendar.html'))
        self.GenerateJsIncludes()
        self.CleanDeletedEnties()


    def build_post(self, post_array):
        post = {}
        post["id"] = post_array[0]
        post["title"] = post_array[1]
        post["body"] = post_array[2]
        post["created"] = post_array[3]
        post["status"] = post_array[4]
        post["keywords"] = post_array[5]
        post["description"] = post_array[6]

        return post


    def get_all_posts(self, visible_only = None):
        c = self.db.cursor()
        if visible_only:
            c.execute("""SELECT id,title,body,created,status,keywords,description FROM posts WHERE status = 1""")
        else:
            c.execute("""SELECT id,title,body,created,status,keywords,description FROM posts""")

        posts = list()
        for post in c:
            posts.append(self.build_post(post))

        return posts

    def get_deleted_posts(self):
        c = self.db.cursor()
        c.execute("SELECT id FROM posts WHERE status == 0")
        posts = list()
        for post in c:
            posts.append(post[0])

        return posts

    def get_updated_posts(self):
        c = self.db.cursor()
        c.execute("""SELECT id,title,body,created,status,keywords,description FROM posts WHERE need_update = 1""")

        posts = list()
        for post in c:
            posts.append(self.build_post(post))

        return posts


    def clean_update_flag(self, post_id):
        self.db.execute("UPDATE posts set need_update = 0 WHERE id = ?", (post_id,))


    def get_post_by_id(self, post_id):
        c = self.db.cursor()
        c.execute("""SELECT id,title,body,created,status,keywords,description FROM posts WHERE id = ?""", (int(post_id),))
        return self.build_post(c.fetchall()[0])


    def GenerateIndexPages(self, tpl):
        page_posts = list()
        page_title = self.config["page_title"]
        page_count = 0

        i = 0
        posts = self.get_all_posts()
        for post in posts:
            if post["status"] == 1:
                page_posts.append(post)

            i = i + 1

            if len(page_posts) == self.config["per_page"] or i == len(posts):
                index_file = self.config["blog_dir"] + "/" + "index"
                if page_count > 0:
                    index_file = index_file + str(page_count)
                index_file = index_file + ".html"

                f = open(index_file, "w")
                f.write(tpl.render({
                            "main_page" : True,
                            "title" : page_title,
                            "page"  : page_count + 1,
                            "pagin" : self.pagination(page_count, len(posts), self.config["per_page"]),
                            "posts" : page_posts,
                            "tags"  : self.tagmap,
                            "hrono" : self.hronomap } ).encode("utf-8"))
                f.close()

                page_count = page_count + 1
                del page_posts[0:len(page_posts)]


    def GenerateJsIncludes(self):
        hrono_tpl = self.env.get_template('left_column.html')
        tags_tpl = self.env.get_template('right_column.html')

        hrono_inc_file = self.config["blog_dir"] + "/" + "calendar.inc.html"
        f = open(hrono_inc_file, "w")
        f.write(hrono_tpl.render({
                    "hrono" : self.hronomap } ).encode("utf-8"))
        f.close()

        tags_inc_file = self.config["blog_dir"] + "/" + "tags.inc.html"
        f = open(tags_inc_file, "w")
        f.write(tags_tpl.render({
                    "tags"  : self.tagmap}).encode("utf-8"))
        f.close()



    def GeneratePostPages(self, tpl):
        for post in self.get_all_posts(True):

            post_file = self.config["blog_dir"] + "/posts/" + str(post["id"]) + ".html"
            f = open(post_file, "w")
            f.write(tpl.render({ 
                        "title" : post["title"],
                        "post": post,
                        "tags" : self.get_post_tags(post["id"]),
                        "hrono" : self.hronomap,
                        }).encode("utf-8"))
            f.close()
                    


    def GenerateTagsPages(self, tpl):
        for tag in self.tagmap:
            tag_file = self.config["blog_dir"] + "/tags/" + str(tag["id"]) + ".html"
            f = open(tag_file, "w")
            f.write(tpl.render({ "tag": tag, 
                                 "posts" : self.get_tag_posts(tag["id"]),
                                 "tags" : self.tagmap,
                                 "hrono" : self.hronomap }).encode("utf-8"))
            f.close()


    def get_posts_for_month(self, year, month):
        c = self.db.cursor();
        c.execute("""SELECT id,title,body,created,status,keywords,description FROM posts WHERE created >= "%s-%s-00" AND created <= "%s-%s-31" """ % ( year, month, year, month));
        posts = list()
        for post in c:
            posts.append(self.build_post(post))

        return posts;

    
    def get_all_tags(self):
        c = self.db.cursor()
        c.execute("SELECT id,name FROM tags");
        
        tags = list()
        for tag in c:
            tags.append({ "id" : tag[0], "name": tag[1] })

        return tags


    def GenerateHronoPages(self, tpl):
        for year in self.hronomap:
            for month in self.hronomap[year]:
                month_file = self.config["blog_dir"] + "/calendar/" + str(year) + "-" + str(month) +".html"
                f = open(month_file, "w")
                f.write(tpl.render({ "month": month,
                                     "year" : year,
                                     "tags" : self.tagmap,
                                     "hrono" : self.hronomap,
                                     "posts" : self.get_posts_for_month(year, month) }).encode("utf-8"))
                f.close()


    def CleanDeletedEnties(self):
        for post in self.get_all_posts():
            if post["status"] == 0:
                post_file = self.config["blog_dir"] + "/posts/" + \
                    str(post["id"]) + ".html"
                try:
                    os.remove(post_file)
                except:
                    pass

    def ftp_try_cd(self, directory):
        try:
            self.ftp.cwd(directory)
        except:
            self.ftp.mkd(directory)
            self.ftp.cwd(directory)


    def ftp_upload_file(self, source, dest):
        f = open(source, "rb")
        self.ftp.storbinary("STOR " + dest, f)
        f.close()


    # todo: сделать аплоад по ftp
    def UploadBlog(self):
        self.ftp = FTP(self.config["ftp_host"])
        if not self.ftp.login(self.config["ftp_user"], self.config["ftp_pass"]):
            print "Cannot connect to ftp";
            exit(0)

        self.ftp_try_cd(self.config["ftp_dir"])

        # залить индексы
        print "Uploading indexies"
        tmp_list = glob.glob(self.config["blog_dir"] + "/index*.html")
        for upfile in tmp_list:
            self.ftp_upload_file(upfile, upfile[upfile.rindex("/")+1:])

        # инклуды календаря и тэгов
        print "Uploading includes"
        self.ftp_upload_file(self.config["blog_dir"]+"/calendar.inc.html","calendar.inc.html")
        self.ftp_upload_file(self.config["blog_dir"]+"/tags.inc.html","tags.inc.html")

        # тэги
        print "Uploading tag pages"
        self.ftp_try_cd("tags")
        tmp_list = glob.glob(self.config["blog_dir"] + "/tags/*.html")
        for upfile in tmp_list:
            self.ftp_upload_file(upfile, upfile[upfile.rindex("/")+1:])
        self.ftp_try_cd("..")
        
        # календарь
        print "Uploading calendar pages"
        self.ftp_try_cd("calendar")
        tmp_list = glob.glob(self.config["blog_dir"] + "/calendar/*.html")
        for upfile in tmp_list:
            self.ftp_upload_file(upfile, upfile[upfile.rindex("/")+1:])
        self.ftp_try_cd("..")

        # посты
        print "Uploading posts"
        self.ftp_try_cd("posts")
        tmp_list = glob.glob(self.config["blog_dir"] + "posts/*.html")
        exist_hash = dict([ ( x, True) for x in self.ftp.nlst() ])
        for upfile in tmp_list:
            if not exist_hash.has_key(upfile[upfile.rindex("/")+1:]):
                self.ftp_upload_file(upfile, upfile[upfile.rindex("/")+1:])

        # удаляем нужные посты
        print "Deleting marked posts"
        exist_hash = dict([ ( x, True) for x in self.ftp.nlst() ])
        for post in self.get_deleted_posts():
            if exist_hash.has_key(str(post) + ".html"):
                self.ftp.delete(str(post) + ".html")

        # обновляем измененные посты
        print "Updating changed posts"
        for post in self.get_updated_posts():
            upfile = self.config["blog_dir"] + "/posts/" + str(post["id"]) + ".html"
            self.ftp_upload_file(upfile, upfile[upfile.rindex("/")+1:])
            self.clean_update_flag(post["id"])
        self.ftp_try_cd("..")


        # загрузка картинок
        print "Uploading images"
        self.ftp_try_cd("imgs")
        tmp_list = glob.glob(self.config["blog_dir"] + "imgs/*")
        exist_hash = dict([ ( x, True) for x in self.ftp.nlst() ])
        for upfile in tmp_list:
            if not exist_hash.has_key(upfile[upfile.rindex("/")+1:]):
                self.ftp_upload_file(upfile, upfile[upfile.rindex("/")+1:])
        self.ftp_try_cd("..")

        # загрузка js и стилей
        print "Uploading assets"

        self.ftp_try_cd("css")
        tmp_list = glob.glob(self.config["blog_dir"] + "css/*")
        for upfile in tmp_list:
            self.ftp_upload_file(upfile, upfile[upfile.rindex("/")+1:])
        self.ftp_try_cd("..")
        
        self.ftp_try_cd("js")
        tmp_list = glob.glob(self.config["blog_dir"] + "js/*")
        for upfile in tmp_list:
            self.ftp_upload_file(upfile, upfile[upfile.rindex("/")+1:])
        self.ftp_try_cd("..")
       

        self.ftp.quit()


    def get_post_tags(self, post_id):
        c = self.db.cursor();
        params = (post_id,)
        c.execute("""SELECT tags.id, tags.name FROM post_tags INNER JOIN tags ON post_tags.tag_id = tags.id WHERE post_tags.post_id = ?""", params)
        return c.fetchall()

    def get_tag_posts(self, tag_id):
        c = self.db.cursor();
        params = (tag_id,)
        c.execute("""SELECT id,title,body,created,status,keywords,description FROM posts INNER JOIN post_tags ON post_tags.post_id = posts.id WHERE posts.status = 1 AND post_tags.tag_id = ?""", params)

        posts = list()
        for post in c:
            posts.append(self.build_post(post))

        return posts
        


    # создать карту тэгов и календарь постов
    def hrono_and_tags_map(self):
        self.tagmap = self.get_all_tags()
        self.hronomap = {}

        for post in self.get_all_posts(True):
            # process time
            post_year = post["created"][0:4]
            post_month = post["created"][5:7]

            if not self.hronomap.has_key(post_year):
                self.hronomap[post_year] = {} 

            if not self.hronomap[post_year].has_key(post_month):
                self.hronomap[post_year][post_month] = list()

            self.hronomap[post_year][post_month].append(post["id"])



    # ниже идут хэлперы для шаблонов
    
    def post_spoil(self, post_id):
        post = self.get_post_by_id(post_id)
        post_body = post["body"]
        spoil_index = post_body.find("<!--spoiler-->")

        if spoil_index != -1:
            return post_body[0:spoil_index] + \
                ("<br/><br/><a href=\"posts/%s.html\">Читать далее...</a>" % post["id"]).decode("utf-8")
        else:
            return post_body

    def post_body(self, post_file):
        f = open(self.config["engine_dir"] + "/" + post_file,"r")
        value = f.read().decode("utf-8")
        f.close()

        return value

    def pagination(self, page, post_count, per_page):
        pages = post_count / per_page;
        nav = {
            "prev" : None,
            "next" : None }
        
        if page >= 1:
            nav["prev"] = page - 1
        if page < pages:
            nav["next"] = page + 1

        return nav

    def get_tags_string(self, post_id):
        tags = self.get_post_tags(post_id)
        tag_string = ""
        for tag in tags:
            tag_string += tag[1]

        return tag_string


    def month_name(self, value):
        monthes = ( "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь")
        return monthes[int(value) - 1 ].decode("utf-8")
            


if __name__ == '__main__':
    usage = """
Usage:
blogger.py add <post_file> - add post from post_file
blogger.py list - print list of current blog posts 
blogger.py edit <post_id> [outfile] - dump post to output or to outfile if speciofied
blogger.py update <post_id> <post_file> - replace post with id = post_id by post_file
blogger.py delete <post_id> - delete post with specified id
blogger.py generate - generate html pages
"""

    blog = Blogger()

    if len(sys.argv) <= 1:
        print usage
        exit(0)

    if sys.argv[1] == "add":
        if len(sys.argv) < 3:
            print "Specify post file to add"
            exit()
        blog.AddPost(sys.argv[2])

    elif sys.argv[1] == "generate":
        blog.GenerateBlog()

    elif sys.argv[1] == "list":
        blog.GetPosts()

    elif sys.argv[1] == "delete":
        blog.DeletePost(sys.argv[2])

    elif sys.argv[1] == "upload":
        blog.UploadBlog()

    elif sys.argv[1] == "edit":
        if len(sys.argv) == 4:
            blog.EditPost(sys.argv[2], sys.argv[3])
        else:
            blog.EditPost(sys.argv[2])

    elif sys.argv[1] == "update":
        blog.UpdatePost(sys.argv[2], sys.argv[3])


