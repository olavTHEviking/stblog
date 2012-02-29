CREATE TABLE posts(
	   id INTEGER,
	   title VARCHAR(512),
	   body TEXT,
	   created DATETIME,
	   status INTEGER DEFAULT 1,
	   keywords VARCHAR(512),
	   description VARCHAR(512),
	   need_update INTEGER DEFAULT 0,
	   PRIMARY KEY(id)
);


CREATE TABLE tags(
	   id INTEGER,
	   name VARCHAR(100),
	   PRIMARY KEY(id)
);

CREATE TABLE post_tags(
	   post_id INTEGER,
	   tag_id INTEGER
);

-- sqlite3 blog_data.db < schema.sql