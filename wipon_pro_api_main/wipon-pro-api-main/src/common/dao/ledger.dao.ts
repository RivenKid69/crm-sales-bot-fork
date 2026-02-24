import {
  BaseEntity,
  Column,
  CreateDateColumn,
  Entity,
  JoinColumn,
  OneToMany,
  OneToOne,
  PrimaryGeneratedColumn,
  UpdateDateColumn,
} from 'typeorm';
import { UserDao } from './user.dao';
import { AccountDao } from './account.dao';
import { InvoiceDao } from './invoice.dao';

@Entity('ledgers')
export class LedgerDao extends BaseEntity {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ type: 'integer', nullable: true, name: 'user_id' })
  user_id: number | null;

  @CreateDateColumn({ name: 'created_at' })
  created_at: Date;

  @UpdateDateColumn({ name: 'updated_at' })
  updated_at: Date;

  @Column({ type: 'varchar', length: 10 })
  code: string;

  @OneToOne(() => UserDao, (user) => user.ledger)
  @JoinColumn({ name: 'user_id' })
  user: UserDao;

  @OneToMany(() => AccountDao, (accounts) => accounts.ledger)
  accounts: AccountDao[];

  @OneToOne(() => InvoiceDao, (invoice) => invoice.ledger)
  invoice: InvoiceDao;
}
